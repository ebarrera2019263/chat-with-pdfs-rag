"""Modelos Pydantic para validación de inputs y forma de las respuestas.

Estos esquemas también alimentan la documentación automática en /docs.
"""

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Documentos
# --------------------------------------------------------------------------- #
class DocumentSummary(BaseModel):
    """Resumen de un documento ingerido (agregado desde sus chunks)."""

    document_id: str = Field(..., description="Identificador único del documento")
    filename: str = Field(..., description="Nombre original del archivo")
    pages: int = Field(..., description="Número de páginas del PDF")
    chunks: int = Field(..., description="Número de chunks generados")


class IngestResult(BaseModel):
    """Resultado de ingerir un único PDF."""

    document_id: str
    filename: str
    pages: int
    chunks: int


class IngestResponse(BaseModel):
    """Respuesta del endpoint de ingesta (uno o varios PDFs)."""

    documents: list[IngestResult]


class DeleteResponse(BaseModel):
    document_id: str
    deleted_chunks: int
    message: str = "Documento eliminado correctamente."


# --------------------------------------------------------------------------- #
# Chat / RAG
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    """Pregunta del usuario para el sistema RAG."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Pregunta en lenguaje natural",
    )
    document_id: str | None = Field(
        None,
        description="Si se indica, limita la búsqueda a ese documento",
    )
    stream: bool = Field(
        True,
        description="Si es true, la respuesta llega por streaming (SSE)",
    )


class Citation(BaseModel):
    """Fuente usada para construir la respuesta."""

    document_id: str
    filename: str
    page: int
    chunk_index: int
    score: float = Field(..., description="Similitud coseno con la pregunta")
    snippet: str = Field(..., description="Fragmento del texto recuperado")


class ChatResponse(BaseModel):
    """Respuesta no-streaming del RAG."""

    answer: str
    citations: list[Citation]


# --------------------------------------------------------------------------- #
# Errores
# --------------------------------------------------------------------------- #
class ErrorResponse(BaseModel):
    detail: str
