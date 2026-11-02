"""P7: bản ghi hỏng bị loại có lý do, không làm hỏng cả job (không cần DB: không có tin sạch)."""
import json

from src.prediction_server.services.ingest.service import IngestService


def test_parse_jsonl_counts_malformed_lines():
    content = b'{"listing_id": "1"}\n\nnot json\n{"listing_id": "2"}\n'
    records, malformed = IngestService.parse_jsonl(content)
    assert [r["listing_id"] for r in records] == ["1", "2"] and malformed == 1


def test_broken_records_are_rejected_with_reasons():
    records = ["text", 5, None, [1], {"listing_id": "x", "images": ["a"]},
               {"listing_id": "no-price", "listing_url": "u", "title": "t"}]
    steps = IngestService(database=None).run(records, malformed=1)  # database=None: không nạp
    clean = steps["clean"]
    assert clean["clean"] == 0 and clean["malformed"] == 1 + 5
    assert steps["load"]["inserted"] == 0
    assert sum(clean["reject_reasons"].values()) == clean["rejected"] == 1
    json.dumps(clean)  # kết quả job phải ra JSON được
