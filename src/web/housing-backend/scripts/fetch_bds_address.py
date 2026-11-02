"""Tải phường/đường của TP.HCM (SG) từ API Batdongsan, lưu nguyên văn vào address_data/.

Chạy từ thư mục housing-backend/housing-backend:

    python scripts/fetch_bds_address.py

Chạy lại được: ID cha đã có trong file JSON đầu ra sẽ được bỏ qua.
Chỉ dùng thư viện chuẩn (urllib) để không cần phụ thuộc ngoài.
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import ClassVar


class BdsAddressFetcher:
    """Gọi API địa chỉ Batdongsan và ghi response nguyên văn ra file JSON."""

    BASE_URL = "https://api.batdongsan.com.vn/bff-seller/locations"
    DATA_DIR = Path(__file__).resolve().parents[3] / "address_data"
    CITY_CODE = "SG"
    # Tên field ID trong response phường mới (đã xác nhận trong sg_new_wards.json)
    NEW_WARD_ID_FIELD = "wardId"
    DELAY_SECONDS = 0.5
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 30
    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    def run(self) -> None:
        """Tải lần lượt 4 file: phường/đường cũ theo quận, phường/đường mới."""
        old_districts = json.loads((self.DATA_DIR / "sg_old.json").read_text(encoding="utf-8"))
        district_ids = [str(d["districtId"]) for d in old_districts]
        self.fetch_children("old-districts/{}/old-wards", "sg_old_wards.json", district_ids)
        self.fetch_children("old-districts/{}/streets", "sg_old_streets.json", district_ids)

        new_wards_path = self.DATA_DIR / "sg_new_wards.json"
        if new_wards_path.exists():
            new_wards = json.loads(new_wards_path.read_text(encoding="utf-8"))
        else:
            new_wards = self.get(f"cities/{self.CITY_CODE}/wards")
            self.save(new_wards_path, new_wards)
        ward_ids = [str(w[self.NEW_WARD_ID_FIELD]) for w in new_wards]
        self.fetch_children("wards/{}/streets", "sg_new_streets.json", ward_ids)

    def fetch_children(self, path_template: str, file_name: str, parent_ids: list[str]) -> None:
        """Gọi API cho từng ID cha còn thiếu, ghi file sau mỗi lần để chạy tiếp được."""
        path = self.DATA_DIR / file_name
        result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        missing = [pid for pid in parent_ids if pid not in result]
        print(f"{file_name}: đã có {len(result)}, cần tải {len(missing)}")
        for parent_id in missing:
            result[parent_id] = self.get(path_template.format(parent_id))
            self.save(path, result)

    def get(self, path: str):
        """GET có nghỉ giữa request và retry giới hạn khi lỗi mạng/5xx/429."""
        url = f"{self.BASE_URL}/{path}"
        request = urllib.request.Request(url, headers=self.HEADERS)
        for attempt in range(1, self.MAX_RETRIES + 1):
            time.sleep(self.DELAY_SECONDS * attempt)
            try:
                with urllib.request.urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                # Lỗi 4xx khác 429 là lỗi phía yêu cầu, retry không giúp gì.
                if error.code < 500 and error.code != 429:
                    raise
                last_error = error
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                last_error = error
            print(f"Lỗi {url} (lần {attempt}/{self.MAX_RETRIES}): {last_error}")
        raise RuntimeError(f"Hết số lần thử: {url}") from last_error

    @staticmethod
    def save(path: Path, data) -> None:
        """Ghi JSON giữ nguyên tiếng Việt, thụt lề 4 như các file có sẵn."""
        path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


if __name__ == "__main__":
    BdsAddressFetcher().run()
