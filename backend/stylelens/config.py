"""Application settings, loaded from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # Infrastructure
    database_url: str = "postgresql+asyncpg://stylelens:stylelens@localhost:5432/stylelens"
    redis_url: str = "redis://localhost:6379/0"
    # "arq" = background worker via Redis; "inline" = run jobs inside the API process
    job_mode: str = "arq"

    # Object storage: "s3" (MinIO / AWS) or "local" (filesystem, for dev without MinIO)
    storage_backend: str = "local"
    storage_local_root: Path = Path(".data/objects")
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_bucket: str = "stylelens"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"

    # Uploads
    max_upload_mb: int = 100

    # LLM layer. Each role can be swapped independently ("provider:model").
    anthropic_api_key: str | None = None
    llm_generation_model: str = "anthropic:claude-sonnet-5-5"
    llm_extraction_model: str = "anthropic:claude-sonnet-5-5"
    llm_vision_model: str = "anthropic:claude-sonnet-5-5"
    llm_fast_model: str = "anthropic:claude-haiku-5-5"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096

    # Embeddings / reranking. "local:<hf model>" or "hash:<dim>" (deterministic, test-only).
    embedding_model: str = "local:BAAI/bge-m3"
    embedding_dim: int = 1024
    reranker_model: str = "local:BAAI/bge-reranker-v2-m3"

    # Retrieval tuning
    retrieval_candidates: int = 50
    rerank_top_k: int = 6
    rerank_threshold: float = 0.15
    rrf_k: int = 60

    # Comparison tuning
    delta_e_exact: float = 1.0
    delta_e_near: float = 3.0

    # Prompts
    prompts_dir: Path = Path(__file__).resolve().parents[2] / "prompts"

    # CORS
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
