"""Punto de entrada de FastAPI.

Un solo servicio sirve la API REST y el frontend estático, para simplificar el
despliegue gratuito (un único proceso en Render/Railway).
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import chat, documents

logger = logging.getLogger("chatbot")

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Devuelve el error real (no un genérico 500) y lo deja en los logs.

    Facilita diagnosticar problemas en producción (p. ej. fallos de conexión a
    servicios externos) mostrando el tipo y mensaje de la excepción.
    """
    logger.error("Error no manejado en %s:\n%s", request.url.path, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


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
