"""Request của POST /ingest dạng JSON."""
from typing import Any

from pydantic import BaseModel

MAX_INGEST_RECORDS = 5000


class IngestBody(BaseModel):
    """`records` để Any: bản ghi hỏng do pipeline loại kèm lý do, không làm 422 cả lô.
    Số bản ghi tối đa kiểm ở router (413), không ở đây (sẽ thành 422)."""

    records: list[Any]
