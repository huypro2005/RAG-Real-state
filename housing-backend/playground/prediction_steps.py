"""Chạy từng tầng của mode dự đoán giá, in đầu vào/đầu ra của mỗi bước (để học luồng).

Cách chạy (trong housing-backend/, đặt PYTHONPATH=. và DATABASE_URL trỏ housing_dev):
    python playground/prediction_steps.py "nhà riêng 60m2 ở Gò Vấp, 3 tầng, ngang 4m"
    python playground/prediction_steps.py "..." --llm     # bước 2 gọi OpenAI thật (tốn ~0,001$)

Không gọi Goong (tiết kiệm hạn mức): bước 3 luôn dùng tâm quận lấy từ bảng listings.
"""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.services.openai_client import openai_client
from app.services.prediction.constants import DISTRICT_NAMES, PROPERTY_TYPES
from app.services.prediction.extractor import FieldExtractor
from app.services.prediction.geocoder import Geocoder
from app.services.prediction.predictor import PriceInput, PricePredictor
from app.services.prediction.schemas import Extraction
from app.services.prediction.text import MessageRules


def show(step: str, value) -> None:
    print(f"\n=== {step} ===\n{value}")


async def main(message: str, use_llm: bool) -> None:
    settings = get_settings()
    print(f"ĐẦU VÀO: {message!r}")

    # Bước 1 — quy tắc bằng code (không tốn tiền): code dùng chúng để kiểm lại LLM
    show("1. MessageRules (code thuần)", {
        "command (reset/ok)": MessageRules.command(message),
        "districts (mã quận)": MessageRules.districts(message),
        "property_types": MessageRules.property_types(message),
        "out_of_domain (thuê/đấu giá)": MessageRules.out_of_domain(message),
        "other_province": MessageRules.other_province(message),
        "area_from_text": MessageRules.area_from_text(message),
    })

    if MessageRules.out_of_domain(message) or MessageRules.other_province(message):
        print("\n→ Code sẽ TỪ CHỐI (thuê/đấu giá/tỉnh khác) dù LLM trích được gì. Dừng ở đây.")
        return

    # Bước 2 — LLM chỉ TRÍCH XUẤT trường, không quyết định gì
    if use_llm:
        extractor = FieldExtractor(openai_client(settings), settings.openai_model)
        extraction = await extractor.extract(message, pending=None, known={})
    else:  # dựng tay từ bước 1 để khỏi gọi OpenAI
        types, districts = MessageRules.property_types(message), MessageRules.districts(message)
        area = MessageRules.area_from_text(message)
        extraction = Extraction(
            property_type=types[0] if types else None,
            district_name=DISTRICT_NAMES[districts[0]] if districts else None,
            area_m2=area[0] if area else None,
        )
    source = "OpenAI thật" if use_llm else "dựng tay, thêm --llm để gọi OpenAI"
    show(f"2. Extraction ({source})", extraction.model_dump(exclude_defaults=True))

    district = MessageRules.districts(extraction.district_name or "")
    if not (extraction.property_type and district and extraction.area_m2):
        print("\n→ Thiếu loại/quận/diện tích: hệ thống sẽ HỎI LẠI, không dự đoán. Dừng ở đây.")
        return

    # Bước 3 — toạ độ (api_key=None: bỏ Goong, dùng tâm quận từ bảng listings)
    engine = create_async_engine(settings.database_url)
    location = await Geocoder(api_key=None, engine=engine).locate(
        DISTRICT_NAMES[district[0]], district[0])
    await engine.dispose()
    show("3. Geocoder.locate", location)

    # Bước 4 — mô hình RandomForest của đồ án 1
    data = PriceInput(
        property_code=PROPERTY_TYPES[extraction.property_type], district_code=district[0],
        area=extraction.area_m2, latitude=location.latitude, longitude=location.longitude,
        floors=extraction.floors, bedrooms=extraction.bedrooms, frontage=extraction.frontage_m,
    )
    show("4a. PriceInput (đặc trưng đưa vào model)", data)
    show("4b. PricePredictor.predict → PriceEstimate", PricePredictor.load().predict(data))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("message")
    parser.add_argument("--llm", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.message, args.llm))
