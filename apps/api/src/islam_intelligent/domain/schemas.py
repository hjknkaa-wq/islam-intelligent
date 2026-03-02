"""Pydantic schema scaffolding."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
