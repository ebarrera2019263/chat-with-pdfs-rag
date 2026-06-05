"""Extracción de texto de PDFs y partición en chunks con metadata.

Se usa pypdf (puro Python, ligero — ideal para deploy gratis). El chunking
trabaja sobre el texto completo del documento manteniendo un mapa de offsets a
páginas, de modo que cada chunk conserva el número de página de donde proviene
(útil para citar fuentes) y a la vez puede cruzar fronteras de página para no
perder contexto.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# Aproximación: ~4 caracteres por token. Evita una dependencia pesada de
# tokenización (tiktoken) que no aporta a un proyecto de portafolio.
CHARS_PER_TOKEN = 4


class PDFProcessingError(Exception):
    """PDF corrupto, vacío o ilegible."""


@dataclass
class Chunk:
    text: str
    page: int
    chunk_index: int


def extract_pages(data: bytes) -> list[str]:
    """Devuelve el texto de cada página del PDF.

    Lanza PDFProcessingError si el archivo no es un PDF válido o no contiene
    texto extraíble (p. ej. un escaneo sin OCR).
    """
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, OSError, ValueError) as exc:
        raise PDFProcessingError(f"No se pudo leer el PDF: {exc}") from exc

    if reader.is_encrypted:
        # Intento de desencriptar con contraseña vacía (muchos PDFs lo permiten).
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 - pypdf lanza tipos variados
            raise PDFProcessingError(
                "El PDF está protegido con contraseña."
            ) from exc

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - una página rota no debe tumbar todo
            pages.append("")

    if not any(p.strip() for p in pages):
        raise PDFProcessingError(
            "El PDF no contiene texto extraíble (¿es un escaneo sin OCR?)."
        )
    return pages


def chunk_pages(
    pages: list[str],
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """Divide el texto del documento en chunks solapados con número de página.

    Construye el texto completo concatenando páginas y recuerda en qué offset
    empieza cada una. Luego desliza una ventana sobre el texto y asigna a cada
    chunk la página donde comienza.
    """
    chunk_chars = max(1, chunk_size_tokens * CHARS_PER_TOKEN)
    overlap_chars = max(0, min(overlap_tokens * CHARS_PER_TOKEN, chunk_chars - 1))
    step = chunk_chars - overlap_chars

    full_parts: list[str] = []
    page_starts: list[int] = []  # offset de inicio de cada página en full_text
    cursor = 0
    for text in pages:
        page_starts.append(cursor)
        normalized = (text or "").strip()
        full_parts.append(normalized)
        cursor += len(normalized) + 1  # +1 por el separador "\n"
    full_text = "\n".join(full_parts)

    chunks: list[Chunk] = []
    index = 0
    pos = 0
    n = len(full_text)
    while pos < n:
        window = full_text[pos : pos + chunk_chars].strip()
        if window:
            # bisect_right - 1 -> índice de la página cuyo inicio <= pos
            page_idx = bisect.bisect_right(page_starts, pos) - 1
            page_number = max(0, page_idx) + 1  # páginas 1-indexadas
            chunks.append(Chunk(text=window, page=page_number, chunk_index=index))
            index += 1
        pos += step

    return chunks
