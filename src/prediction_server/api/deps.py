"""Dependency của FastAPI: lấy Container của app và kiểm tra X-API-Key."""
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from src.prediction_server.core.container import Container
from src.prediction_server.core.security import ApiKeyAuth


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def require_api_key(
    container: ContainerDep, x_api_key: Annotated[str | None, Header()] = None
) -> None:
    """401 khi thiếu/sai khóa; 503 khi server chưa được cấu hình khóa nào."""
    auth = ApiKeyAuth(container.settings.prediction_server_api_key)
    if not auth.configured:
        raise HTTPException(503, "Server chưa cấu hình PREDICTION_SERVER_API_KEY")
    if not auth.matches(x_api_key):
        raise HTTPException(401, "Thiếu hoặc sai X-API-Key")
