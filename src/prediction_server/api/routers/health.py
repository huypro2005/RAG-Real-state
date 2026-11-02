"""GET /health: không cần khóa, luôn trả 200 để người vận hành thấy lý do khi có sự cố."""
import psycopg
from fastapi import APIRouter

from src.prediction_server.api.deps import ContainerDep

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health(container: ContainerDep) -> dict:
    info = {"status": "ok", "db": "ok", "db_schema_missing": False, "model": None,
            "jobs_running": [job["job_id"] for job in container.store.running()]}
    try:
        if not container.runs.schema_ready():
            return {**info, "status": "degraded", "db_schema_missing": True}
        active = container.runs.active()
        info["retrain_running_in_db"] = container.runs.running_count()
    except psycopg.Error as error:
        return {**info, "status": "degraded", "db": f"error: {error}"}
    if active is None:
        return {**info, "status": "degraded", "model": "no_active_model"}
    loaded = container.registry.current()
    info["model"] = {
        "run_id": active["id"], "candidate": active["best_candidate"],
        "r2_log": active["metrics"].get("r2_log"), "trained_at": active["finished_at"],
        "loaded_in_memory": loaded.run_id if loaded else None,
    }
    return info
