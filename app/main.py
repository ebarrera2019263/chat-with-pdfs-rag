"""Punto de entrada de FastAPI.

Un solo servicio sirve la API REST y el frontend estático, para simplificar el
despliegue gratuito (un único proceso en Render/Railway).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import chat, documents

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Chatea con tus PDFs",
    description=(
        "API RAG: ingiere PDFs, los indexa en Qdrant con embeddings de Voyage "
        "AI y responde preguntas con Anthropic Claude citando las fuentes."
    ),
    version="1.0.0",
)

app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health", tags=["meta"], summary="Healthcheck")
async def health() -> dict:
    """Comprueba que el servicio está vivo y la config se cargó."""
    settings = get_settings()
    return {
        "status": "ok",
        "model": settings.anthropic_model,
        "embedding_model": settings.voyage_model,
        "collection": settings.qdrant_collection,
    }


# El frontend estático se monta al final para no tapar las rutas de la API.
if STATIC_DIR.exists():

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
