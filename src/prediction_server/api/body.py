"""BodyReader: đọc body của POST /ingest với trần dung lượng (413 nếu vượt)."""
import json
from collections.abc import AsyncIterator

from fastapi import HTTPException, Request
from starlette.formparsers import MultiPartParser


class BodyReader:
    """Đọc theo khối, dừng ngay khi vượt `max_bytes` kể cả khi không có Content-Length."""

    def __init__(self, request: Request, max_bytes: int):
        self.request = request
        self.max_bytes = max_bytes

    def check_length(self) -> None:
        declared = self.request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            raise HTTPException(413, f"Body vượt {self.max_bytes} byte")

    async def read_json(self) -> object:
        self.check_length()
        body = b"".join([chunk async for chunk in self._chunks()])
        try:
            return json.loads(body)
        except ValueError as error:
            raise HTTPException(422, f"JSON không hợp lệ: {error}") from error

    async def read_upload(self) -> bytes | None:
        """Nội dung trường `file` của multipart; None nếu thiếu trường đó."""
        self.check_length()
        form = await MultiPartParser(self.request.headers, self._chunks()).parse()
        upload = form.get("file")
        return None if upload is None or isinstance(upload, str) else await upload.read()

    async def _chunks(self) -> AsyncIterator[bytes]:
        total = 0
        async for chunk in self.request.stream():
            total += len(chunk)
            if total > self.max_bytes:
                raise HTTPException(413, f"Body vượt {self.max_bytes} byte")
            yield chunk
