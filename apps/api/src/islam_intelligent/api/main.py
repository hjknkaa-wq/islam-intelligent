"""FastAPI application entrypoint."""

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from fastapi import FastAPI

from ..domain.schemas import HealthResponse
from .routes import evidence, kg, rag, sources, spans

app = FastAPI(title="Islam Intelligent API")

# Include routers
app.include_router(sources.router)
app.include_router(spans.router)
app.include_router(kg.router)
app.include_router(kg.router)
app.include_router(rag.router)
app.include_router(evidence.router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
