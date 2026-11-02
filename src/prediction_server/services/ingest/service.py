"""IngestService: tin crawl thô -> làm sạch -> listings (upsert) -> FK địa chỉ -> POI.

Dùng lại ListingCleaner và ListingLoader của src/pipeline (cùng input cho cùng số dòng sạch với
`python -m src.pipeline`). Dữ liệu thô chỉ nằm trong bộ nhớ của job, không ghi đĩa, không lưu DB.
"""
import json
import threading

from src.pipeline.listing_cleaner import ListingCleaner
from src.pipeline.listing_loader import ListingLoader
from src.prediction_server.db.connection import Database

REJECTED_SAMPLE = 50  # số tin bị loại kèm lý do để xem nhanh trong kết quả job


class IngestService:
    """Một lần nạp = một lần gọi run(); các lần nạp nối đuôi nhau (khóa) cho khỏi giẫm chân."""

    _lock = threading.Lock()

    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def parse_jsonl(content: bytes) -> tuple[list, int]:
        """(các dòng JSON hợp lệ, số dòng hỏng). Dòng trống bị bỏ qua như ListingCleaner."""
        records, malformed = [], 0
        for line in content.decode("utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
        return records, malformed

    def run(self, records: list, malformed: int = 0) -> dict:
        """Trả số liệu từng bước, cùng tên khóa với bước 1-4 của `python -m src.pipeline`."""
        # Bản ghi không phải object JSON hoặc có giá trị lồng nhau không thể là tin crawl hợp lệ:
        # đếm là dòng hỏng thay vì để cả job đổ vì một bản ghi.
        usable = [r for r in records if isinstance(r, dict)
                  and not any(isinstance(v, (dict, list)) for v in r.values())]
        malformed += len(records) - len(usable)
        steps = {}
        with self._lock:
            clean, rejected = ListingCleaner().clean(usable) if usable else (None, None)
            steps["clean"] = self._clean_report(usable, malformed, clean, rejected)
            if clean is not None and len(clean):
                with self.database.connect() as conn:
                    loader = ListingLoader(conn)
                    steps["load"] = loader.upsert(clean)
                    steps["addresses"] = loader.link_addresses()
                    steps["poi"] = loader.refresh_spatial()
            else:
                steps["load"] = {"rows_in": 0, "inserted": 0, "updated": 0, "unchanged": 0}
        return steps

    @staticmethod
    def _clean_report(usable: list, malformed: int, clean, rejected) -> dict:
        if clean is None:
            return {"input_lines": malformed, "malformed": malformed, "duplicates_removed": 0,
                    "unique_listings": 0, "rejected": 0, "clean": 0, "reject_reasons": {}}
        sample = rejected.head(REJECTED_SAMPLE).astype(object)  # pd.NA không ra JSON được
        return {
            "input_lines": len(usable) + malformed, "malformed": malformed,
            "duplicates_removed": len(usable) - len(clean) - len(rejected),
            "unique_listings": len(clean) + len(rejected), "rejected": len(rejected),
            "clean": len(clean), "reject_reasons": rejected["reason"].value_counts().to_dict(),
            "rejected_sample": sample.where(sample.notna(), None).to_dict("records"),
        }
