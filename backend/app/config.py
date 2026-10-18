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
    roles_dir: Path = REPO_DIR / "roles"
    supabase_url: str | None = None
    supabase_jwt_secret: str | None = None
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"
    handbook_effort: str = "medium"  # Opus 5.5's default; raise to "high" if drafts miss rules
    apprentice_model: str = "claude-opus-5-5"
    apprentice_effort: str = "medium"
    apprentice_samples: int = 5  # self-consistency: confidence = share of samples that agree
    backtest_concurrency: int = 16
    reprobation_concurrency: int = 48  # re-certifying the frozen record should take minutes, not half an hour
    judge_model: str = "claude-opus-5-5"
    judge_effort: str = "medium"
    repredict_samples: int = 1  # re-predicting the backlog after a rule edit: one sample keeps it quick and cheap
    backlog_size: int = 50
    external_agent_timeout_s: float = 30.0
    inline_worker: bool = True  # dev: the API runs queued jobs itself, no separate worker process
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Keys pseudonyms, match-key hashes and token encryption. Must be set outside dev.
    app_secret: str = "dev-only-insecure-secret"
    api_url: str = "http://127.0.0.1:8000"
    web_url: str = "http://localhost:3000"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Where Newt reaches people besides the app (docs/NEEDS_JAKE.md). Each channel is off until configured.
    slack_client_id: str | None = None
    slack_client_secret: str | None = None
    slack_signing_secret: str | None = None
    slack_api_url: str = "https://slack.com/api"
    teams_app_id: str | None = None
    teams_app_password: str | None = None
    teams_token_url: str = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
    teams_openid_url: str = "https://login.botframework.com/v1/.well-known/openidconfiguration"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "Newt <newt@example.com>"
    inbound_email_domain: str | None = None  # replies go to newt+<token>@this domain
    inbound_email_secret: str | None = None  # the inbound-parse webhook sends it in X-Newt-Inbound

    def secret(self) -> bytes:
        if self.env != "dev" and self.app_secret == "dev-only-insecure-secret":
            raise RuntimeError("APP_SECRET must be set outside dev")
        return self.app_secret.encode()


@lru_cache
def get_settings() -> Settings:
    return Settings()
