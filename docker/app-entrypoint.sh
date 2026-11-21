#!/bin/sh
# Entrypoint của image Python. Mỗi service đọc .env riêng của nó (DATABASE_URL trỏ localhost:5433 để
# chạy trên Windows); trong Docker, DB là service "db" cổng 5432, nên chỉ thay phần "@host:port/" của
# URL và giữ nguyên user, mật khẩu, tên DB, driver.
set -e
if [ -n "$DATABASE_URL" ]; then
  DATABASE_URL=$(printf '%s' "$DATABASE_URL" | sed -E 's#@[^/@]+/#@db:5432/#')
  export DATABASE_URL
fi
exec "$@"
