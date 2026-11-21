"""FastAPI app của Prediction Server (mỏng: dựng app, vòng đời, lỗi DB, gắn router).

Chạy (tại thư mục gốc dự án, .venv gốc):
    python -m uvicorn src.web.prediction_server.main:app --port 8100
hoặc chạy thẳng file (nút Run của VS Code): python src/web/prediction_server/main.py
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Chạy thẳng file thì sys.path chỉ có thư mục chứa file, thiếu gốc dự án nên `import src...` lỗi.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.web.prediction_server.api.router import api_router
from src.web.prediction_server.core.container import Container
from src.web.prediction_server.core.settings import ServerSettings, get_settings


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    """Nhận settings để test dựng app với cấu hình riêng."""
    container = Container(settings or get_settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        container.runner.start()
        yield
        container.runner.stop()

    app = FastAPI(title="Prediction Server", lifespan=lifespan)
    app.state.container = container

    @app.exception_handler(psycopg.errors.UndefinedTable)
    async def schema_missing(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse({"detail": "db_schema_missing: chạy alembic upgrade head"}, 503)

    @app.exception_handler(psycopg.OperationalError)
    async def db_down(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"detail": f"Không kết nối được database: {error}"}, 503)

    app.include_router(api_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=8100)
