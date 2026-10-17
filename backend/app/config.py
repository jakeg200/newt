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
    apprentice_model: str = "claude-opus-5-5"
    apprentice_effort: str = "medium"
    apprentice_samples: int = 5  # self-consistency: confidence = share of samples that agree
    backtest_concurrency: int = 16
    external_agent_timeout_s: float = 30.0
    inline_worker: bool = True  # dev: the API runs queued jobs itself, no separate worker process
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Keys pseudonyms, match-key hashes and token encryption. Must be set outside dev.
    app_secret: str = "dev-only-insecure-secret"
    api_url: str = "http://127.0.0.1:8000"
    web_url: str = "http://localhost:3000"
    google_client_id: str | None = None
    google_client_secret: str | None = None

    def secret(self) -> bytes:
        if self.env != "dev" and self.app_secret == "dev-only-insecure-secret":
            raise RuntimeError("APP_SECRET must be set outside dev")
        return self.app_secret.encode()


@lru_cache
def get_settings() -> Settings:
    return Settings()
