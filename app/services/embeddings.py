"""Generación de embeddings con Voyage AI.

Voyage distingue el tipo de entrada: 'document' para los chunks que se indexan
y 'query' para las preguntas. Eso mejora la calidad del retrieval.
"""

from __future__ import annotations

import voyageai

from app.config import get_settings

# Límite conservador de Voyage por request; lo usamos para batchear.
_MAX_BATCH = 128


class EmbeddingError(Exception):
    """Fallo al generar embeddings (API caída, cuota, etc.)."""


_client: voyageai.Client | None = None


def _get_client() -> voyageai.Client:
    global _client
    if _client is None:
        _client = voyageai.Client(api_key=get_settings().voyage_api_key)
    return _client


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embeddings para chunks a indexar, en batches para eficiencia."""
    return _embed(texts, input_type="document")


def embed_query(text: str) -> list[float]:
    """Embedding de una pregunta del usuario."""
    return _embed([text], input_type="query")[0]


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    settings = get_settings()
    client = _get_client()
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), _MAX_BATCH):
            batch = texts[start : start + _MAX_BATCH]
            result = client.embed(
                batch, model=settings.voyage_model, input_type=input_type
            )
            vectors.extend(result.embeddings)
    except Exception as exc:  # noqa: BLE001 - el SDK lanza varios tipos
        raise EmbeddingError(f"Error generando embeddings con Voyage: {exc}") from exc
    return vectors
