"""pois_name_trgm: index trigram trên tên POI không dấu (tra địa điểm có tên, named-places.md)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14

unaccent() chỉ STABLE nên không dùng trực tiếp trong index; bọc trong hàm IMMUTABLE có chỉ rõ
từ điển. PlaceResolver dùng đúng biểu thức immutable_unaccent(lower(name)) để index có tác dụng.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION immutable_unaccent(value text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, value) $$
    """)
    op.execute(
        "CREATE INDEX pois_name_trgm ON pois "
        "USING gin (immutable_unaccent(lower(name)) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS pois_name_trgm")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
