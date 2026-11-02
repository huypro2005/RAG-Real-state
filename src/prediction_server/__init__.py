"""Prediction Server: dự đoán giá, nạp tin thô, tự retrain và tự chọn mô hình tốt nhất.

Dùng chung PostgreSQL và code với backend chatbot: model SQLAlchemy/migration Alembic là nguồn
chuẩn của cấu trúc DB, còn PriceInput/PriceEstimate/PricePredictor được import lại từ backend
(không chép) nên cần đưa thư mục backend vào sys.path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "src" / "web" / "housing-backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
