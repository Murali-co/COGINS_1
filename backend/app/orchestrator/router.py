from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List, Dict, Any

from app.auth.utils import get_current_user
from app.orchestrator.schemas import WorkflowSchema, WorkflowCreateRequest
from app.orchestrator.enums import WorkflowState
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.capabilities import CapabilityRegistry
from app.orchestrator.tools.registry import ToolRegistry
from app.orchestrator.tools.runner import ToolRunner
from app.orchestrator.tools.parser import LLMToolParser
from app.orchestrator.tools.schemas import ToolDefinitionSchema, ToolExecutionRequest, ToolExecutionResult
from app.orchestrator.tools.exceptions import (
    UnknownToolError,
    UnauthorizedToolError,
    InvalidToolArgumentsError,
    ToolExecutionTimeoutError,
    ToolExecutionError,
    MalformedToolRequestError
)
from app.llm.ollama_client import OllamaClient
from app.auth.models import DBManager

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

@router.get("/capabilities", response_model=List[Dict[str, Any]])
async def list_capabilities(current_user: dict = Depends(get_current_user)):
    """List all safe, approved capabilities available to the orchestrator."""
    caps = CapabilityRegistry.get_all()
    return [
        {"name": c["name"], "description": c["description"]}
        for c in caps.values()
    ]

# ==================== TOOL FRAMEWORK ENDPOINTS ====================
@router.get("/tools", response_model=List[ToolDefinitionSchema])
async def list_tools(current_user: dict = Depends(get_current_user)):
    """List all registered local tools with schemas, permissions, and status."""
    tools = ToolRegistry.get_all_tools()
    return [t.to_schema() for t in tools.values()]

@router.post("/tools/execute", response_model=ToolExecutionResult)
async def execute_tool_directly(
    request: ToolExecutionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Execute a registered tool directly with schema validation and permission enforcement."""
    try:
        result = await ToolRunner.execute_tool(user_dict=current_user, request=request)
        return result
    except UnknownToolError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedToolError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidToolArgumentsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ToolExecutionTimeoutError as e:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(e))
    except ToolExecutionError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/tools/invoke-llm", response_model=Dict[str, Any])
async def invoke_llm_tool(
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Prompt the local LLM agent to select and execute the optimal tool for a task."""
    user_prompt = payload.get("prompt", "").strip()
    if not user_prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt cannot be empty.")

    tools = ToolRegistry.get_enabled_tools()
    tool_descriptions = "\n".join([
        f"- '{t.name}': {t.description} (Inputs: {t.input_schema_class.model_json_schema().get('properties', {})})"
        for t in tools.values()
    ])

    system_prompt = (
        "You are an AI Agent with access to local tool capabilities. "
        "Select the single best tool for the user task and format your response ONLY in valid JSON.\n"
        "Example JSON format:\n"
        "{\n"
        '  "tool_name": "search_jobs",\n'
        '  "arguments": {"search_term": "Python Engineer"}\n'
        "}\n"
        "Return ONLY JSON."
    )

    llm_prompt = f"""
Available Local Tools:
{tool_descriptions}

User Task:
"{user_prompt}"

Select tool and return JSON:
"""
    try:
        raw_output = await OllamaClient.generate(prompt=llm_prompt, system=system_prompt, format="json")
        parsed_payload = LLMToolParser.parse_tool_call(raw_output)

        tool_request = ToolExecutionRequest(
            tool_name=parsed_payload.tool_name,
            arguments=parsed_payload.arguments
        )

        exec_result = await ToolRunner.execute_tool(user_dict=current_user, request=tool_request)
        return {
            "llm_selected_tool": parsed_payload.tool_name,
            "arguments": parsed_payload.arguments,
            "result": exec_result.model_dump()
        }
    except MalformedToolRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UnknownToolError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedToolError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidToolArgumentsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ToolExecutionTimeoutError as e:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(e))
    except ToolExecutionError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# ==================== WORKFLOW ENDPOINTS ====================
@router.post("/workflows", response_model=WorkflowSchema, status_code=status.HTTP_201_CREATED)
async def create_and_run_workflow(
    request: WorkflowCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create and execute an Orchestrator workflow for a given user goal."""
    if not request.goal.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Goal cannot be empty."
        )
        
    workflow = await OrchestratorEngine.run_workflow(
        user_id=current_user["id"],
        request=request
    )
    return workflow

@router.get("/workflows", response_model=List[WorkflowSchema])
async def list_user_workflows(current_user: dict = Depends(get_current_user)):
    """Retrieve all orchestrator workflows created by the current user."""
    workflows = DBManager.get_user_workflows(current_user["id"])
    return [WorkflowSchema(**wf) for wf in workflows]

@router.get("/workflows/{workflow_id}", response_model=WorkflowSchema)
async def get_workflow_details(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed workflow status, error info, and task execution breakdown."""
    wf_dict = DBManager.get_workflow(workflow_id)
    if not wf_dict or wf_dict.get("user_id") != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found."
        )
    return WorkflowSchema(**wf_dict)

@router.post("/workflows/{workflow_id}/cancel", response_model=WorkflowSchema)
async def cancel_workflow_execution(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Cancel an active or pending orchestrator workflow."""
    wf_dict = DBManager.get_workflow(workflow_id)
    if not wf_dict or wf_dict.get("user_id") != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found."
        )

    current_status = wf_dict.get("status")
    if current_status in [WorkflowState.COMPLETED.value, WorkflowState.FAILED.value, WorkflowState.CANCELLED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workflow is already in terminal state '{current_status}'."
        )

    OrchestratorEngine.cancel_workflow(workflow_id)
    DBManager.finish_workflow(workflow_id, WorkflowState.CANCELLED.value, error="Workflow cancelled by user.")
    
    updated_wf = DBManager.get_workflow(workflow_id)
    return WorkflowSchema(**updated_wf)
