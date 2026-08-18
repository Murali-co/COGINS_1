import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from app.orchestrator.tools.registry import ToolRegistry, ToolEntry
from app.orchestrator.tools.runner import ToolRunner
from app.orchestrator.tools.parser import LLMToolParser
from app.orchestrator.tools.permissions import ToolPermission
from app.orchestrator.tools.schemas import ToolExecutionRequest
from app.orchestrator.tools.exceptions import (
    UnknownToolError,
    UnauthorizedToolError,
    InvalidToolArgumentsError,
    ToolExecutionTimeoutError,
    ToolExecutionError,
    MalformedToolRequestError
)
from pydantic import BaseModel
from app.auth.models import DBManager

def get_auth_user(client, email: str, is_admin: bool = False):
    client.post("/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Test Tool User"
    })
    user = DBManager.get_user_by_email(email)
    DBManager.verify_email(user["id"])

    if is_admin:
        DBManager.promote_user_to_admin(email)

    login_res = client.post("/auth/login", json={
        "email": email,
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    csrf_token = login_res.cookies.get("csrf_token")
    headers = {"Authorization": f"Bearer {token}"}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
    user_dict = DBManager.get_user_by_email(email)
    return user_dict, headers


@pytest.mark.asyncio
async def test_valid_tool_call(client):
    """Test valid tool execution via ToolRunner and API endpoint."""
    user_dict, headers = get_auth_user(client, "tool_valid@example.com")

    # 1. Direct Runner Execution
    req = ToolExecutionRequest(
        tool_name="search_jobs",
        arguments={"search_term": "Python Developer", "limit": 3}
    )
    result = await ToolRunner.execute_tool(user_dict=user_dict, request=req)
    assert result.status == "SUCCESS"
    assert result.tool_name == "search_jobs"
    assert "jobs" in result.output

    # 2. API Endpoint Execution
    api_res = client.post("/orchestrator/tools/execute", json=req.model_dump(), headers=headers)
    assert api_res.status_code == 200
    res_json = api_res.json()
    assert res_json["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_invalid_arguments(client):
    """Test schema validation failure for invalid or missing required tool arguments."""
    user_dict, headers = get_auth_user(client, "tool_invalid@example.com")

    # missing required 'search_term' argument for search_jobs
    req = ToolExecutionRequest(
        tool_name="search_jobs",
        arguments={"limit": "not_an_int"}
    )

    with pytest.raises(InvalidToolArgumentsError):
        await ToolRunner.execute_tool(user_dict=user_dict, request=req)

    # API returns 400 Bad Request
    api_res = client.post("/orchestrator/tools/execute", json=req.model_dump(), headers=headers)
    assert api_res.status_code == 400
    assert "invalid arguments" in api_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unauthorized_tool(client):
    """Test permission denial when non-admin user attempts admin tool execution."""
    user_dict, headers = get_auth_user(client, "tool_unauth@example.com", is_admin=False)

    class DummyInput(BaseModel):
        pass
    class DummyOutput(BaseModel):
        status: str

    async def dummy_admin_handler(user_id: int, **kwargs):
        return {"status": "admin_success"}

    ToolRegistry.register(
        name="admin_secret_tool",
        description="Admin only sensitive tool",
        input_schema_class=DummyInput,
        output_schema_class=DummyOutput,
        handler=dummy_admin_handler,
        permission=ToolPermission.ADMIN
    )

    req = ToolExecutionRequest(tool_name="admin_secret_tool", arguments={})

    with pytest.raises(UnauthorizedToolError):
        await ToolRunner.execute_tool(user_dict=user_dict, request=req)

    api_res = client.post("/orchestrator/tools/execute", json=req.model_dump(), headers=headers)
    assert api_res.status_code == 403


@pytest.mark.asyncio
async def test_unknown_tool(client):
    """Test calling an unregistered tool name."""
    user_dict, headers = get_auth_user(client, "tool_unknown@example.com")
    req = ToolExecutionRequest(tool_name="non_existent_fake_tool", arguments={})

    with pytest.raises(UnknownToolError):
        await ToolRunner.execute_tool(user_dict=user_dict, request=req)

    api_res = client.post("/orchestrator/tools/execute", json=req.model_dump(), headers=headers)
    assert api_res.status_code == 404


@pytest.mark.asyncio
async def test_tool_timeout(client):
    """Test timeout enforcement when tool handler exceeds timeout limit."""
    user_dict, headers = get_auth_user(client, "tool_timeout@example.com")

    class DummyInput(BaseModel):
        pass
    class DummyOutput(BaseModel):
        status: str

    async def slow_handler(user_id: int, **kwargs):
        await asyncio.sleep(2.0)
        return {"status": "success"}

    ToolRegistry.register(
        name="slow_test_tool",
        description="Slow tool for timeout testing",
        input_schema_class=DummyInput,
        output_schema_class=DummyOutput,
        handler=slow_handler,
        permission=ToolPermission.READ,
        timeout=0.1  # 100ms timeout
    )

    req = ToolExecutionRequest(tool_name="slow_test_tool", arguments={})

    with pytest.raises(ToolExecutionTimeoutError):
        await ToolRunner.execute_tool(user_dict=user_dict, request=req, max_retries=0)

    api_res = client.post("/orchestrator/tools/execute", json=req.model_dump(), headers=headers)
    assert api_res.status_code == 504


@pytest.mark.asyncio
async def test_tool_failure(client):
    """Test handling unhandled handler runtime exceptions."""
    user_dict, headers = get_auth_user(client, "tool_failure@example.com")

    class DummyInput(BaseModel):
        pass
    class DummyOutput(BaseModel):
        status: str

    async def failing_handler(user_id: int, **kwargs):
        raise RuntimeError("Database connection crashed during tool execution")

    ToolRegistry.register(
        name="failing_test_tool",
        description="Failing tool for error testing",
        input_schema_class=DummyInput,
        output_schema_class=DummyOutput,
        handler=failing_handler,
        permission=ToolPermission.READ,
        timeout=10.0
    )

    req = ToolExecutionRequest(tool_name="failing_test_tool", arguments={})

    with pytest.raises(ToolExecutionError):
        await ToolRunner.execute_tool(user_dict=user_dict, request=req, max_retries=0)

    api_res = client.post("/orchestrator/tools/execute", json=req.model_dump(), headers=headers)
    assert api_res.status_code == 500


def test_malformed_llm_tool_request():
    """Test LLMToolParser handling invalid JSON and malformed LLM outputs."""
    # 1. Completely invalid JSON
    with pytest.raises(MalformedToolRequestError):
        LLMToolParser.parse_tool_call("This is plain text response without JSON.")

    # 2. Missing tool_name field
    with pytest.raises(MalformedToolRequestError):
        LLMToolParser.parse_tool_call('{"some_key": "some_value"}')

    # 3. Valid JSON tool call with markdown codeblock
    raw_llm_output = '''```json
{
  "tool_name": "search_jobs",
  "arguments": {
    "search_term": "Python Engineer"
  }
}
```'''
    parsed = LLMToolParser.parse_tool_call(raw_llm_output)
    assert parsed.tool_name == "search_jobs"
    assert parsed.arguments["search_term"] == "Python Engineer"
