"""Response của các đường tạo/xem job nền."""
from pydantic import BaseModel


class JobAccepted(BaseModel):
    job_id: str
