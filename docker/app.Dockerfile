# Image Python dùng chung cho backend, Prediction Server và giao diện pipeline.
# Build context = gốc dự án vì Prediction Server import code của backend, pipeline và notebook.
# Chạy trên Linux nên không bị Windows Smart App Control chặn file .pyd (scikit-learn, asyncpg).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# libgomp1: OpenMP cho lightgbm/xgboost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Chỉ chép code cần chạy; mô hình (.joblib) và dữ liệu được mount từ máy khi chạy
COPY src/__init__.py src/__init__.py
COPY src/web/housing-backend src/web/housing-backend
COPY src/web/prediction_server src/web/prediction_server
COPY src/pipeline src/pipeline
COPY src/notebook/predictionEDA/db_to_training src/notebook/predictionEDA/db_to_training
COPY docker/app-entrypoint.sh /usr/local/bin/app-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/app-entrypoint && chmod +x /usr/local/bin/app-entrypoint

ENTRYPOINT ["app-entrypoint"]
