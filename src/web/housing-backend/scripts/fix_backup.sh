#!/usr/bin/env bash
# Bản bash của fix_backup.ps1 (Linux / macOS / Git Bash).
#   PGPASSWORD=... ./scripts/fix_backup.sh /duong/dan/data_ultilities.sql [thu_muc_ra]
# Biến tùy chọn: PGHOST, PGPORT, PGUSER (mặc định localhost / 5432 / postgres)
#                SKIP_VECTOR=1  ép bỏ qua pgvector dù máy đã cài
# Máy chưa cài pgvector thì script tự bỏ extension "vector" và bảng rag.listing_embeddings.
set -euo pipefail

BACKUP="$(realpath "$1")"
OUT_DIR="$(realpath "${2:-.}")"
TMP_DB=housing_fix_tmp
SQL_DIR="$(cd "$(dirname "$0")/../db" && pwd)"
export PGHOST="${PGHOST:-localhost}" PGPORT="${PGPORT:-5432}" PGUSER="${PGUSER:-postgres}"

dropdb --if-exists "$TMP_DB"
createdb "$TMP_DB"
trap 'rm -f "${LIST:-}"; dropdb --if-exists "$TMP_DB"' EXIT

HAS_VECTOR=$(psql -d "$TMP_DB" -tAc "SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'")
RESTORE_OPTS=(--no-owner --no-privileges --exit-on-error)
USE_VECTOR=1

if [ "${SKIP_VECTOR:-0}" = "1" ] || [ "$HAS_VECTOR" = "0" ]; then
    USE_VECTOR=0
    echo "pgvector chưa cài (hoặc SKIP_VECTOR=1): bỏ extension vector và bảng rag.listing_embeddings"
    LIST="$(mktemp)"
    # Dòng bắt đầu bằng ';' trong mục lục thì pg_restore bỏ qua
    pg_restore -l "$BACKUP" \
      | sed -E '/EXTENSION - vector|EXTENSION vector|[[:space:]]rag[[:space:]]listing_embeddings[[:space:]]/ s/^/;/' > "$LIST"
    echo "Đã bỏ $(grep -cE '^;[0-9]' "$LIST") mục trong mục lục backup (dự kiến 6)"
    RESTORE_OPTS+=(-L "$LIST")
fi

pg_restore -d "$TMP_DB" "${RESTORE_OPTS[@]}" "$BACKUP"
(cd "$SQL_DIR" && psql -d "$TMP_DB" -1 -v ON_ERROR_STOP=1 -f move_to_public.sql)

mkdir -p "$OUT_DIR"
pg_dump -Fc --no-owner --no-privileges -f "$OUT_DIR/housing_public.dump" "$TMP_DB"
pg_dump -Fp --no-owner --no-privileges -f "$OUT_DIR/housing_public.sql"  "$TMP_DB"
echo "Xong: $OUT_DIR/housing_public.dump và $OUT_DIR/housing_public.sql"

if [ "$USE_VECTOR" = "0" ]; then
    echo "LƯU Ý: file mới KHÔNG có bảng listing_embeddings (cần pgvector)."
    echo "File backup gốc vẫn còn đủ. Cài pgvector rồi chạy lại script (không SKIP_VECTOR) sẽ ra bản đầy đủ."
fi
