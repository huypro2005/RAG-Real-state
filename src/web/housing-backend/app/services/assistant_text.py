"""Câu cố định do CODE viết (không qua LLM): chào hỏi, giới thiệu năng lực, chuyển chế độ.

Dùng chung cho hai chatbot. LLM chỉ gán intent; nội dung các câu này không phụ thuộc người dùng
nên không thể bị prompt injection làm đổi.
"""

from typing import Literal

Mode = Literal["recommendation", "prediction"]
Kind = Literal["chitchat", "other_mode"]

THANKS = {  # đã có kết quả: trả lời một câu, không lặp lại khối giới thiệu
    "prediction": "Rất vui được giúp bạn! Bạn có thể hỏi thêm về kết quả hoặc thử giả định (vd. "
                  "\"nếu thêm 1 tầng thì sao\").",
    "recommendation": "Rất vui được giúp bạn! Bạn có thể hỏi thêm về các căn vừa gợi ý.",
}
# Chatbot dự đoán hỏi lần lượt trường tuỳ chọn, kèm lý do ngắn (đều là đặc trưng thật của mô hình)
OPTIONAL_QUESTIONS = {
    "frontage": "Mặt tiền rộng bao nhiêu mét? (mô hình dùng mặt tiền để ước tính sát hơn)",
    "floors": "Nhà có mấy tầng? (mô hình dùng số tầng để ước tính sát hơn)",
    "bedrooms": "Có mấy phòng ngủ? (mô hình dùng số phòng ngủ để ước tính sát hơn)",
    "address": "Bạn cho mình tên đường hoặc dự án cụ thể được không? "
               "(giúp tính khoảng cách tới trung tâm chính xác hơn)",
}
OPTIONAL_HINT = " Gõ \"bỏ qua\" nếu không rõ, hoặc gõ ok để dự đoán ngay."
RELATIVE_UNKNOWN = "Mình chưa biết {} hiện tại. Bạn cho mình số hiện có trước rồi thử giả định nhé."
READY_PROMPT = "Gõ ok để mình dự đoán giá, hoặc bổ sung thêm thông tin nếu bạn muốn."
GREETING = "Chào bạn! Mình là trợ lý bất động sản TP.HCM (địa giới cũ, trước sáp nhập 2025)."
ABILITIES = {
    "recommendation": (
        "Mình giúp bạn tìm tin đang bán theo ngân sách, khu vực, loại nhà, tiện ích quanh đó; "
        "hỏi chi tiết, so sánh các tin vừa gợi ý và xem giá rao có sát ước tính của mô hình không."
    ),
    "prediction": (
        "Mình ước tính giá một bất động sản của bạn bằng mô hình học máy từ tin đăng "
        "batdongsan.com.vn, và giải thích kết quả; bạn cũng có thể thử giả định (\"nếu...\")."
    ),
}
EXAMPLES = {  # các câu người dùng có thể gõ
    "recommendation": ["Căn hộ Quận 7 dưới 3 tỷ", "Nhà Gò Vấp 3 phòng ngủ gần trường học",
                       "Căn 2 giá có cao so với thị trường không?"],
    "prediction": ["Nhà riêng 60m2 Gò Vấp, 3 phòng ngủ", "Nếu thêm 1 tầng thì giá thế nào?",
                   "Quận 2 hay quận 7 có giá cao hơn?"],
}
PREDICTION_TOPICS = (  # chatbot dự đoán trả lời "câu hỏi khác" bằng danh sách này
    "Mình trả lời được các câu hỏi về: vì sao ra mức giá này, khoảng tham khảo là gì, mô hình "
    "dùng gì, so sánh giá giữa các quận, cần bổ sung gì để ước tính chính xác hơn."
)
SUGGESTIONS = {  # câu trả lời nhanh (chip) của chatbot dự đoán theo bước đang hỏi
    "property": ["Căn hộ chung cư", "Nhà riêng", "Nhà mặt phố", "Đất"],
    "confirm": ["Đúng", "Không phải"],
    "predicted": ["Vì sao giá này?", "Mô hình dùng gì?", "Bắt đầu lại"],
}
SWITCH = {  # mode hiện tại -> câu chỉ sang tab còn lại (hội thoại ở tab này được giữ nguyên)
    "prediction": (
        "Để tìm tin đang bán, bạn chuyển sang tab *Gợi ý* nhé. "
        "Ở tab này mình chỉ ước tính giá một bất động sản; thông tin bạn đã nhập vẫn được giữ."
    ),
    "recommendation": (
        "Để ước tính giá một căn của bạn, bạn chuyển sang tab *Dự đoán giá* nhé. "
        "Ở tab này mình tìm tin đang bán; điều kiện tìm của bạn vẫn được giữ."
    ),
}


def assistant_reply(kind: Kind, mode: Mode, short: bool = False) -> str:
    """Câu chào kèm ví dụ (kind="chitchat") hoặc câu chuyển chế độ (kind="other_mode").

    short: đã có kết quả (dự đoán / tin gợi ý) thì chỉ đáp một câu."""
    if kind == "other_mode":
        return SWITCH[mode]
    if short:
        return THANKS[mode]
    examples = (f"- {example}" for example in EXAMPLES[mode])
    return "\n".join([f"{GREETING} {ABILITIES[mode]}", "Bạn có thể thử:", *examples])
