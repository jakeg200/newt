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


@lru_cache
def get_settings() -> Settings:
    return Settings()
