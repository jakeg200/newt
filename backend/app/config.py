from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    env: str = "dev"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'dev.db').as_posix()}"
    task_types_dir: Path = REPO_DIR / "task_types"
    supabase_url: str | None = None
    supabase_jwt_secret: str | None = None
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"
    handbook_effort: str = "medium"  # Opus 5.5's default; raise to "high" if drafts miss rules
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
