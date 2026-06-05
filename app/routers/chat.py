"""Endpoint de chat: el corazón del RAG (retrieval + generación)."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.schemas import ChatRequest, ChatResponse, Citation
from app.services import embeddings, llm, vectorstore
from app.services.vectorstore import SearchHit

router = APIRouter(prefix="/chat", tags=["chat"])

_SNIPPET_LEN = 280


def _retrieve(req: ChatRequest) -> list[SearchHit]:
    """Embebe la pregunta y recupera los chunks más relevantes de Qdrant."""
    settings = get_settings()
    vectorstore.ensure_collection()
    try:
        query_vector = embeddings.embed_query(req.question)
    except embeddings.EmbeddingError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    try:
        hits = vectorstore.search(
            vector=query_vector,
            top_k=settings.top_k,
            document_id=req.document_id,
        )
    except vectorstore.VectorStoreError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    # Filtra ruido por debajo del umbral de similitud.
    return [h for h in hits if h.score >= settings.min_score]


def _citations(hits: list[SearchHit]) -> list[Citation]:
    return [
        Citation(
            document_id=h.document_id,
            filename=h.filename,
            page=h.page,
            chunk_index=h.chunk_index,
            score=round(h.score, 4),
            snippet=(h.text[:_SNIPPET_LEN] + "…")
            if len(h.text) > _SNIPPET_LEN
            else h.text,
        )
        for h in hits
    ]


@router.post(
    "",
    summary="Preguntar al RAG (streaming SSE o respuesta JSON)",
    response_model=ChatResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat(req: ChatRequest):
    """Recupera contexto y genera la respuesta de Claude con citas.

    - `stream=true` (por defecto): respuesta por Server-Sent Events.
    - `stream=false`: respuesta JSON completa.
    """
    hits = _retrieve(req)
    citations = _citations(hits)

    if not req.stream:
        try:
            answer = llm.generate(req.question, hits)
        except llm.LLMError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        return ChatResponse(answer=answer, citations=citations)

    return StreamingResponse(
        _sse_stream(req, citations, hits),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse_event(payload: dict) -> str:
    """Formatea un evento SSE con un objeto JSON en el campo data."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_stream(
    req: ChatRequest,
    citations: list[Citation],
    hits: list[SearchHit],
) -> Iterator[str]:
    """Emite primero las fuentes, luego los tokens y al final 'done'."""
    # 1) Fuentes primero, para que el frontend pueda mostrarlas mientras llega
    #    la respuesta.
    yield _sse_event(
        {"type": "sources", "citations": [c.model_dump() for c in citations]}
    )
    # 2) Tokens de la respuesta.
    try:
        for token in llm.generate_stream(req.question, hits):
            yield _sse_event({"type": "token", "text": token})
    except llm.LLMError as exc:
        yield _sse_event({"type": "error", "detail": str(exc)})
        return
    # 3) Señal de fin.
    yield _sse_event({"type": "done"})
