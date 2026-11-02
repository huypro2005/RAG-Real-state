"""GET /jobs/{job_id}: trạng thái và số liệu từng bước của job nền."""
from fastapi import APIRouter, Depends, HTTPException

from src.prediction_server.api.deps import ContainerDep, require_api_key

router = APIRouter(prefix="/api/v1", tags=["jobs"], dependencies=[Depends(require_api_key)])


@router.get("/jobs/{job_id}")
def get_job(job_id: str, container: ContainerDep) -> dict:
    job = container.store.get(job_id)
    if job is None:
        raise HTTPException(404, "Không có job này (có thể đã mất do server khởi động lại)")
    return job
