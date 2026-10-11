from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Any

from backend.app.security.sandbox import code_sandbox

router = APIRouter(prefix="/coding", tags=["Secure Coding Sandbox"])

class CodeExecutionRequest(BaseModel):
    code: str
    language: Optional[str] = "python"
    input_data: Optional[str] = None
    test_cases: Optional[List[Any]] = None

@router.post("/run")
@router.post("/execute")
async def execute_code_snippet(req: CodeExecutionRequest):
    """
    Safely executes student code inside an isolated sandbox with resource quotas,
    AST safety inspection, environment scrubbing, and strict execution timeouts.
    """
    return code_sandbox.execute_code(
        code=req.code,
        language=req.language or "python",
        input_data=req.input_data
    )

