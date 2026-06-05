"""Configuración central de la aplicación.

Todas las claves y URLs se leen de variables de entorno (o de un archivo .env
en desarrollo local) usando pydantic-settings, de forma que el código nunca
contiene secretos.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración tipada de la app. Falla rápido si falta una clave."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Anthropic (LLM de respuestas) ---
    anthropic_api_key: str = Field(..., description="API key de Anthropic")
    anthropic_model: str = Field(
        "claude-sonnet-4-6",
        description="Modelo de Claude a usar para generar respuestas",
    )
    anthropic_max_tokens: int = Field(1024, description="Máx. tokens de respuesta")

    # --- Voyage AI (embeddings) ---
    voyage_api_key: str = Field(..., description="API key de Voyage AI")
    voyage_model: str = Field("voyage-3", description="Modelo de embeddings")
    embedding_dim: int = Field(
        1024, description="Dimensión de los vectores (voyage-3 = 1024)"
    )

    # --- Qdrant Cloud (vector DB) ---
    qdrant_url: str = Field(..., description="URL del cluster de Qdrant Cloud")
    qdrant_api_key: str = Field(..., description="API key de Qdrant Cloud")
    qdrant_collection: str = Field(
        "pdf_chunks", description="Nombre de la colección en Qdrant"
    )

    # --- Ingesta / chunking ---
    chunk_size_tokens: int = Field(800, description="Tamaño objetivo del chunk")
    chunk_overlap_tokens: int = Field(100, description="Solapamiento entre chunks")
    max_upload_mb: int = Field(20, description="Tamaño máximo por PDF en MB")

    # --- Retrieval ---
    top_k: int = Field(5, description="Número de chunks a recuperar por consulta")
    min_score: float = Field(
        0.3, description="Score mínimo de similitud para considerar un chunk relevante"
    )


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de Settings."""
    return Settings()
