"""POST /ingest: nhận tin crawl thô, chạy nền, trả 202 kèm job_id."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from src.prediction_server.api.body import BodyReader
from src.prediction_server.api.deps import ContainerDep, require_api_key
from src.prediction_server.schemas.ingest import MAX_INGEST_RECORDS, IngestBody
from src.prediction_server.schemas.jobs import JobAccepted
from src.prediction_server.services.ingest.service import IngestService

router = APIRouter(prefix="/api/v1", tags=["ingest"], dependencies=[Depends(require_api_key)])


@router.post("/ingest", status_code=202, response_model=JobAccepted)
async def ingest(request: Request, container: ContainerDep):
    """JSON `{records: [...]}` hoặc multipart với trường `file` là JSON Lines.

    Quá MAX_INGEST_BYTES hoặc quá 5.000 bản ghi: 413 (cả hai đường), đúng cấu trúc: 422.
    """
    reader = BodyReader(request, container.settings.max_ingest_bytes)
    malformed = 0
    if request.headers.get("content-type", "").startswith("multipart/"):
        content = await reader.read_upload()
        if content is None:
            raise HTTPException(422, "Thiếu trường file trong multipart")
        records, malformed = IngestService.parse_jsonl(content)
    else:
        try:
            records = IngestBody.model_validate(await reader.read_json()).records
        except ValidationError as error:
            raise HTTPException(422, str(error)) from error
    if len(records) > MAX_INGEST_RECORDS:
        raise HTTPException(413, f"Tối đa {MAX_INGEST_RECORDS} bản ghi mỗi lần")
    return {"job_id": container.runner.submit_ingest(records, malformed)}
