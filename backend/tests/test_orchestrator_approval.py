import pytest
import uuid
from unittest.mock import patch
from app.orchestrator.enums import WorkflowState, TaskState
from app.orchestrator.capabilities import CapabilityRegistry
from app.orchestrator.schemas import PlanSchema, PlanTaskSpec
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
async def test_external_action_requires_approval_and_resumes(client):
    """Test that external_action tasks pause in AWAITING_APPROVAL and run after approval."""
    user_id, headers = get_auth_user(client, "action_approval@example.com", "Approval User")

    # Mock planner to generate an external action task
    mock_plan = PlanSchema(tasks=[
        PlanTaskSpec(
            task_id="task_read",
            task_type="analyze_resume",
            description="Analyze candidate resume",
            input={},
            dependencies=[]
        ),
        PlanTaskSpec(
            task_id="task_external",
            task_type="submit_job_application",
            description="Submit job application",
            input={"company": "Acme Corp", "title": "Senior Engineer"},
            dependencies=["task_read"]
        )
    ])

    with patch("app.orchestrator.planner.GoalPlanner.create_plan", return_value=mock_plan):
        # 1. Trigger workflow execution
        payload = {"goal": "Apply for Senior Engineer job"}
        res = client.post("/orchestrator/workflows", json=payload, headers=headers)
        assert res.status_code == 201
        data = res.json()
        wf_id = data["workflow_id"]

        # Workflow MUST enter AWAITING_APPROVAL state because task_external has risk_tier="external_action"
        assert data["status"] == WorkflowState.AWAITING_APPROVAL.value

        # Verify first read_only task completed, but external action task is AWAITING_APPROVAL
        tasks_map = {t["task_id"]: t for t in data["tasks"]}
        assert tasks_map["task_read"]["status"] == TaskState.COMPLETED.value
        assert tasks_map["task_external"]["status"] == TaskState.AWAITING_APPROVAL.value

        # 2. Query pending approval endpoint
        pending_res = client.get(f"/orchestrator/workflows/{wf_id}/pending-approval", headers=headers)
        assert pending_res.status_code == 200
        pending_data = pending_res.json()
        assert len(pending_data) == 1
        assert pending_data[0]["task_id"] == "task_external"
        assert pending_data[0]["risk_tier"] == "external_action"

        # 3. Approve task
        approve_res = client.post(f"/orchestrator/workflows/{wf_id}/approve", json={"task_id": "task_external"}, headers=headers)
        assert approve_res.status_code == 200
        approved_data = approve_res.json()

        # Workflow should now be COMPLETED
        assert approved_data["status"] == WorkflowState.COMPLETED.value
        tasks_map_after = {t["task_id"]: t for t in approved_data["tasks"]}
        assert tasks_map_after["task_external"]["status"] == TaskState.COMPLETED.value


@pytest.mark.asyncio
async def test_external_action_rejection(client):
    """Test rejecting an external_action task cancels the workflow."""
    user_id, headers = get_auth_user(client, "action_reject@example.com", "Reject User")

    mock_plan = PlanSchema(tasks=[
        PlanTaskSpec(
            task_id="task_ext",
            task_type="submit_job_application",
            description="Submit job application",
            input={"company": "Globex", "title": "DevOps Engineer"},
            dependencies=[]
        )
    ])

    with patch("app.orchestrator.planner.GoalPlanner.create_plan", return_value=mock_plan):
        res = client.post("/orchestrator/workflows", json={"goal": "Apply to Globex"}, headers=headers)
        assert res.status_code == 201
        data = res.json()
        wf_id = data["workflow_id"]
        assert data["status"] == WorkflowState.AWAITING_APPROVAL.value

        # Reject task
        reject_res = client.post(f"/orchestrator/workflows/{wf_id}/reject", json={"task_id": "task_ext"}, headers=headers)
        assert reject_res.status_code == 200
        rejected_data = reject_res.json()

        assert rejected_data["status"] == WorkflowState.CANCELLED.value


@pytest.mark.asyncio
async def test_auto_approve_external_actions_preference(client):
    """Test auto_approve_external_actions preference allows external_action tasks to execute automatically."""
    user_id, headers = get_auth_user(client, "auto_approve@example.com", "Auto Approve User")

    # Turn on auto_approve_external_actions
    pref_res = client.patch("/auth/preferences/auto-approve-external", json={"auto_approve_external_actions": True}, headers=headers)
    assert pref_res.status_code == 200
    assert pref_res.json()["auto_approve_external_actions"] is True

    mock_plan = PlanSchema(tasks=[
        PlanTaskSpec(
            task_id="task_ext",
            task_type="submit_job_application",
            description="Submit job application",
            input={"company": "Initech", "title": "Systems Architect"},
            dependencies=[]
        )
    ])

    with patch("app.orchestrator.planner.GoalPlanner.create_plan", return_value=mock_plan):
        res = client.post("/orchestrator/workflows", json={"goal": "Apply to Initech"}, headers=headers)
        assert res.status_code == 201
        data = res.json()

        # Because auto_approve=True, workflow completes directly without pausing!
        assert data["status"] == WorkflowState.COMPLETED.value
        assert data["tasks"][0]["status"] == TaskState.COMPLETED.value
