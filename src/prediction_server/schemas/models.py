"""Response của nhóm đường /models."""
from pydantic import BaseModel


class ActivateResult(BaseModel):
    active_run_id: int
    candidate: str
