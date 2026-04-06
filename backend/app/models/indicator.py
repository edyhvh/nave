from datetime import datetime
from typing import Any

from pydantic import BaseModel


class IndicatorResponse(BaseModel):
    name: str
    as_of: datetime
    source: str
    data: dict[str, Any]
    cached: bool


class ErrorResponse(BaseModel):
    error: str
    message: str
    status_code: int
    details: dict | None = None
    correlation_id: str | None = None
