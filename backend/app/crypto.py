"""Encryption for stored credentials (OAuth refresh tokens, agent signing secrets)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class DecryptError(ValueError):
    pass


def _fernet() -> Fernet:
    key = hashlib.sha256(b"connection-tokens:" + get_settings().secret()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptError("stored credentials can't be read") from exc
