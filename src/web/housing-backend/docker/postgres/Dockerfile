# PostgreSQL 18 + PostGIS + pgvector, chạy trong Docker (thay cho Postgres cài trực tiếp trên Windows:
# Windows Smart App Control chặn vector.dll không có chữ ký, còn trong container Linux thì không bị).
# Image PostGIS chưa có pgvector -> cài thêm từ repo PGDG có sẵn trong image.
FROM postgis/postgis:18-3.6

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-18-pgvector \
 && apt-get clean
