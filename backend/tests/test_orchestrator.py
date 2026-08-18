import pytest
import asyncio
import uuid
from unittest.mock import patch, AsyncMock
from app.orchestrator.enums import WorkflowState, TaskState
from app.orchestrator.schemas import WorkflowCreateRequest, PlanSchema, PlanTaskSpec
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.planner import GoalPlanner
from app.orchestrator.capabilities import CapabilityRegistry
from app.auth.models import DBManager

def get_auth_user(client, email: str, name: str = "Test User"):
    client.post("/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": name
    })
    user = DBManager.get_user_by_email(email)
    DBManager.verify_email(user["id"])
    login_res = client.post("/auth/login", json={
        "email": email,
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    csrf_token = login_res.cookies.get("csrf_token")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf_token
    }
    return user["id"], headers

@pytest.mark.asyncio
async def test_simple_workflow(client):
    """Test executing a simple single-step workflow end-to-end."""
    user_id, headers = get_auth_user(client, "orch_simple@example.com", "Simple User")

    payload = {
        "goal": "Analyze my resume skills",
        "max_steps": 5,
        "execution_timeout": 30.0,
        "max_retries": 1
    }
    response = client.post("/orchestrator/workflows", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()

    assert data["workflow_id"] is not None
    assert data["status"] == WorkflowState.COMPLETED.value
    assert len(data["tasks"]) > 0
    assert data["tasks"][0]["status"] == TaskState.COMPLETED.value


@pytest.mark.asyncio
async def test_multi_step_workflow(client):
    """Test executing a multi-step workflow with task dependency output piping."""
    user_id, headers = get_auth_user(client, "orch_multi@example.com", "Multi Step User")

    mock_plan = PlanSchema(tasks=[
        PlanTaskSpec(
            task_id="task_1",
            task_type="analyze_resume",
            description="Extract skills",
            input={},
            dependencies=[]
        ),
        PlanTaskSpec(
            task_id="task_2",
            task_type="search_and_match_jobs",
            description="Match jobs for extracted skills",
            input={"search_term": "Python Developer"},
            dependencies=["task_1"]
        )
    ])

    with patch.object(GoalPlanner, "create_plan", new_callable=AsyncMock) as mock_create_plan:
        mock_create_plan.return_value = mock_plan

        payload = {
            "goal": "Analyze resume and match Python jobs",
            "max_steps": 5,
            "execution_timeout": 30.0,
            "max_retries": 1
        }
        response = client.post("/orchestrator/workflows", json=payload, headers=headers)
        assert response.status_code == 201
        data = response.json()

        assert data["status"] == WorkflowState.COMPLETED.value
        assert len(data["tasks"]) == 2
        assert data["tasks"][0]["status"] == TaskState.COMPLETED.value
        assert data["tasks"][1]["status"] == TaskState.COMPLETED.value


@pytest.mark.asyncio
async def test_invalid_plan_unapproved_capability(client):
    """Test handling of invalid plan containing an unapproved capability."""
    user_id, headers = get_auth_user(client, "orch_invalid@example.com", "Invalid Plan User")

    mock_plan = PlanSchema(tasks=[
        PlanTaskSpec(
            task_id="task_1",
            task_type="unapproved_malicious_capability",
            description="Execute prohibited operation",
            input={},
            dependencies=[]
        )
    ])

    with patch.object(GoalPlanner, "create_plan", new_callable=AsyncMock) as mock_create_plan:
        mock_create_plan.return_value = mock_plan

        req = WorkflowCreateRequest(goal="Do prohibited stuff", max_steps=5)
        workflow = await OrchestratorEngine.run_workflow(user_id=user_id, request=req)

        assert workflow.status == WorkflowState.FAILED
        assert "not approved" in workflow.error.lower() or "unapproved capability" in workflow.error.lower() or "failed" in workflow.error.lower()


@pytest.mark.asyncio
async def test_failed_task(client):
    """Test graceful failure handling when a capability task fails after retries."""
    user_id, headers = get_auth_user(client, "orch_fail@example.com", "Failed Task User")

    mock_plan = PlanSchema(tasks=[
        PlanTaskSpec(
            task_id="task_1",
            task_type="analyze_resume",
            description="Analysis task",
            input={},
            dependencies=[]
        )
    ])

    with patch.object(GoalPlanner, "create_plan", new_callable=AsyncMock) as mock_create_plan, \
         patch.object(CapabilityRegistry, "execute", side_effect=RuntimeError("Capability database error")):
        mock_create_plan.return_value = mock_plan

        req = WorkflowCreateRequest(goal="Analyze resume", max_retries=1)
        workflow = await OrchestratorEngine.run_workflow(user_id=user_id, request=req)

        assert workflow.status == WorkflowState.FAILED
        assert "Capability database error" in workflow.error
        assert len(workflow.tasks) == 1
        assert workflow.tasks[0].status == TaskState.FAILED


@pytest.mark.asyncio
async def test_task_retry_logic(client):
    """Test task retry mechanism on transient errors."""
    user_id, headers = get_auth_user(client, "orch_retry@example.com", "Retry User")

    mock_plan = PlanSchema(tasks=[
        PlanTaskSpec(
            task_id="task_1",
            task_type="analyze_resume",
            description="Transient task",
            input={},
            dependencies=[]
        )
    ])

    calls = 0
    async def mock_execute_transient(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("Transient network issue")
        return {"status": "success", "skills": ["Python"]}

    with patch.object(GoalPlanner, "create_plan", new_callable=AsyncMock) as mock_create_plan, \
         patch.object(CapabilityRegistry, "execute", side_effect=mock_execute_transient):
        mock_create_plan.return_value = mock_plan

        req = WorkflowCreateRequest(goal="Analyze resume", max_retries=2)
        workflow = await OrchestratorEngine.run_workflow(user_id=user_id, request=req)

        assert workflow.status == WorkflowState.COMPLETED
        assert calls == 2
        assert workflow.tasks[0].status == TaskState.COMPLETED


@pytest.mark.asyncio
async def test_workflow_execution_timeout(client):
    """Test workflow execution timeout enforcement."""
    user_id, headers = get_auth_user(client, "orch_timeout@example.com", "Timeout User")

    mock_plan = PlanSchema(tasks=[
        PlanTaskSpec(
            task_id="task_1",
            task_type="analyze_resume",
            description="Long running task",
            input={},
            dependencies=[]
        )
    ])

    async def mock_slow_execute(*args, **kwargs):
        await asyncio.sleep(2.0)
        return {"status": "success"}

    with patch.object(GoalPlanner, "create_plan", new_callable=AsyncMock) as mock_create_plan, \
         patch.object(CapabilityRegistry, "execute", side_effect=mock_slow_execute):
        mock_create_plan.return_value = mock_plan

        req = WorkflowCreateRequest(goal="Analyze resume", execution_timeout=0.1, max_retries=0)
        workflow = await OrchestratorEngine.run_workflow(user_id=user_id, request=req)

        assert workflow.status == WorkflowState.FAILED
        assert "timed out" in workflow.error.lower()


@pytest.mark.asyncio
async def test_workflow_cancellation(client):
    """Test cancelling a workflow via API endpoint."""
    user_id, headers = get_auth_user(client, "orch_cancel@example.com", "Cancel User")

    wf_id = str(uuid.uuid4())
    DBManager.save_workflow({
        "workflow_id": wf_id,
        "user_id": user_id,
        "goal": "Test cancel goal",
        "status": "RUNNING"
    })

    cancel_res = client.post(f"/orchestrator/workflows/{wf_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["status"] == WorkflowState.CANCELLED.value

    get_res = client.get(f"/orchestrator/workflows/{wf_id}", headers=headers)
    assert get_res.json()["status"] == WorkflowState.CANCELLED.value
