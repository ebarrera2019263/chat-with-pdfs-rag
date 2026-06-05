"""Endpoints de gestión de documentos: ingesta, listado y borrado."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.config import get_settings
from app.schemas import (
    DeleteResponse,
    DocumentSummary,
    IngestResponse,
    IngestResult,
)
from app.services import embeddings, pdf, vectorstore

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir e ingerir uno o varios PDFs",
)
async def ingest_documents(files: list[UploadFile] = File(...)) -> IngestResponse:
    """Extrae texto, hace chunking, genera embeddings e indexa en Qdrant."""
    settings = get_settings()
    vectorstore.ensure_collection()

    results: list[IngestResult] = []
    for upload in files:
        if upload.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"'{upload.filename}' no es un PDF.",
            )

        data = await upload.read()
        size_mb = len(data) / (1024 * 1024)
        if size_mb > settings.max_upload_mb:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"'{upload.filename}' pesa {size_mb:.1f} MB; el máximo es "
                    f"{settings.max_upload_mb} MB."
                ),
            )

        try:
            pages = pdf.extract_pages(data)
            chunks = pdf.chunk_pages(
                pages,
                settings.chunk_size_tokens,
                settings.chunk_overlap_tokens,
            )
        except pdf.PDFProcessingError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{upload.filename}': {exc}",
            ) from exc

        if not chunks:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{upload.filename}' no produjo texto indexable.",
            )

        try:
            vectors = embeddings.embed_documents([c.text for c in chunks])
        except embeddings.EmbeddingError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, detail=str(exc)
            ) from exc

        document_id = str(uuid.uuid4())
        try:
            vectorstore.upsert_chunks(
                document_id=document_id,
                filename=upload.filename or "documento.pdf",
                pages=len(pages),
                chunks=chunks,
                vectors=vectors,
            )
        except vectorstore.VectorStoreError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, detail=str(exc)
            ) from exc

        results.append(
            IngestResult(
                document_id=document_id,
                filename=upload.filename or "documento.pdf",
                pages=len(pages),
                chunks=len(chunks),
            )
        )

    return IngestResponse(documents=results)


@router.get(
    "",
    response_model=list[DocumentSummary],
    summary="Listar documentos ingeridos",
)
async def list_documents() -> list[DocumentSummary]:
    try:
        vectorstore.ensure_collection()
        docs = vectorstore.list_documents()
    except vectorstore.VectorStoreError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [DocumentSummary(**doc) for doc in docs]


@router.delete(
    "/{document_id}",
    response_model=DeleteResponse,
    summary="Borrar un documento y sus vectores",
)
async def delete_document(document_id: str) -> DeleteResponse:
    try:
        vectorstore.ensure_collection()
        deleted = vectorstore.delete_document(document_id)
    except vectorstore.VectorStoreError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if deleted == 0:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No existe un documento con ese id.",
        )
    return DeleteResponse(document_id=document_id, deleted_chunks=deleted)
