from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.deps import SessionDep
from app.api.v1.routes import router as v1_router
from app.core.config import get_settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # KHÔNG gọi create_all ở đây: schema do Alembic quản lý (alembic upgrade head)
    yield
    await engine.dispose()


app = FastAPI(title="Housing API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health(session: SessionDep):
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
