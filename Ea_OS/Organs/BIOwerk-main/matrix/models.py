from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import time, uuid

def new_id() -> str:
    return str(uuid.uuid4())

def now() -> float:
    return time.time()

class Msg(BaseModel):
    id: str = Field(default_factory=new_id)
    ts: float = Field(default_factory=now)
    origin: str
    target: str
    intent: str
    input: Dict[str, Any] = {}
    api_version: Optional[str] = Field(
        default="v1",
        description="API version for this message. Defaults to v1 for backward compatibility."
    )

class Reply(BaseModel):
    id: str
    ts: float
    agent: str
    ok: bool
    output: Dict[str, Any]
    state_hash: str
    api_version: Optional[str] = Field(
        default="v1",
        description="API version used to generate this reply. Matches the request version."
    )
