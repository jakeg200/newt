"""Logging that never carries message bodies or documents.

Our own log lines name ids and counts only. SQLAlchemy's engine logger is pinned to WARNING,
because at INFO it prints bound parameters, which would include case snapshots.
"""

import logging

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs can carry message ids
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"agent_onboarding.{name}")
