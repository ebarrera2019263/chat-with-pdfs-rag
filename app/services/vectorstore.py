"""Capa de acceso a Qdrant Cloud: indexar, buscar, listar y borrar.

Qdrant es la única fuente de verdad persistente. La lista de documentos se
deriva agregando los payloads de los puntos (no se mantiene un registro aparte),
lo que mantiene el deploy en un solo servicio sin base de datos extra.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import get_settings
from app.services.pdf import Chunk


class VectorStoreError(Exception):
    """Fallo de conexión u operación en Qdrant."""


@dataclass
class SearchHit:
    document_id: str
    filename: str
    page: int
    chunk_index: int
    text: str
    score: float


_client: QdrantClient | None = None
_collection_ready = False


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        settings = get_settings()
        try:
            _client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"No se pudo conectar a Qdrant: {exc}") from exc
    return _client


def ensure_collection() -> None:
    """Crea la colección si no existe (idempotente)."""
    global _collection_ready
    if _collection_ready:
        return
    settings = get_settings()
    client = _get_client()
    try:
        exists = client.collection_exists(settings.qdrant_collection)
        if not exists:
            client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=qm.VectorParams(
                    size=settings.embedding_dim,
                    distance=qm.Distance.COSINE,
                ),
            )
            # Índice sobre document_id para filtrar y borrar por documento.
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name="document_id",
                field_schema=qm.PayloadSchemaType.KEYWORD,
            )
        _collection_ready = True
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(f"Error preparando la colección: {exc}") from exc


def upsert_chunks(
    document_id: str,
    filename: str,
    pages: int,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> None:
    """Guarda los vectores + metadata + texto de cada chunk."""
    settings = get_settings()
    client = _get_client()
    points = [
        qm.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "document_id": document_id,
                "filename": filename,
                "pages": pages,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
            },
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    try:
        client.upsert(collection_name=settings.qdrant_collection, points=points)
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(f"Error guardando vectores en Qdrant: {exc}") from exc


def search(
    vector: list[float],
    top_k: int,
    document_id: str | None = None,
) -> list[SearchHit]:
    """Búsqueda por similitud, opcionalmente filtrada a un documento."""
    settings = get_settings()
    client = _get_client()
    query_filter = None
    if document_id:
        query_filter = qm.Filter(
            must=[
                qm.FieldCondition(
                    key="document_id", match=qm.MatchValue(value=document_id)
                )
            ]
        )
    try:
        response = client.query_points(
            collection_name=settings.qdrant_collection,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(f"Error consultando Qdrant: {exc}") from exc

    hits: list[SearchHit] = []
    for point in response.points:
        payload = point.payload or {}
        hits.append(
            SearchHit(
                document_id=payload.get("document_id", ""),
                filename=payload.get("filename", ""),
                page=payload.get("page", 0),
                chunk_index=payload.get("chunk_index", 0),
                text=payload.get("text", ""),
                score=point.score,
            )
        )
    return hits


def list_documents() -> list[dict]:
    """Agrega los puntos por document_id para listar los PDFs subidos."""
    settings = get_settings()
    client = _get_client()
    docs: dict[str, dict] = {}
    next_page = None
    try:
        while True:
            records, next_page = client.scroll(
                collection_name=settings.qdrant_collection,
                limit=256,
                offset=next_page,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                doc_id = payload.get("document_id")
                if not doc_id:
                    continue
                entry = docs.setdefault(
                    doc_id,
                    {
                        "document_id": doc_id,
                        "filename": payload.get("filename", "desconocido"),
                        "pages": payload.get("pages", 0),
                        "chunks": 0,
                    },
                )
                entry["chunks"] += 1
            if next_page is None:
                break
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(f"Error listando documentos: {exc}") from exc
    return sorted(docs.values(), key=lambda d: d["filename"].lower())


def delete_document(document_id: str) -> int:
    """Borra todos los chunks de un documento. Devuelve cuántos se borraron."""
    settings = get_settings()
    client = _get_client()
    selector = qm.Filter(
        must=[
            qm.FieldCondition(
                key="document_id", match=qm.MatchValue(value=document_id)
            )
        ]
    )
    try:
        before = client.count(
            collection_name=settings.qdrant_collection,
            count_filter=selector,
            exact=True,
        ).count
        if before == 0:
            return 0
        client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=qm.FilterSelector(filter=selector),
        )
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(f"Error borrando el documento: {exc}") from exc
    return before
