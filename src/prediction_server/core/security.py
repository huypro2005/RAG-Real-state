"""Kiểm tra khóa X-API-Key."""
import secrets

from pydantic import SecretStr


class ApiKeyAuth:
    """So khóa gửi lên với PREDICTION_SERVER_API_KEY bằng so sánh thời gian không đổi."""

    def __init__(self, expected: SecretStr | None):
        self.expected = expected

    @property
    def configured(self) -> bool:
        return self.expected is not None

    def matches(self, provided: str | None) -> bool:
        return bool(provided) and self.configured and secrets.compare_digest(
            provided, self.expected.get_secret_value())
