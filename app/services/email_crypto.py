"""
ImageShrink Pro V2 Email & OAuth Token Cryptography.
Secures Google OAuth refresh tokens at rest using AES-GCM / Fernet authenticated encryption.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger("imageshrink.crypto")


def _get_encryption_key() -> bytes:
    """
    Retrieves or derives a 32-byte URL-safe base64 key for Fernet encryption.
    If GMAIL_TOKEN_ENCRYPTION_KEY is set and valid, it is used directly.
    Otherwise, a stable 256-bit key is derived from settings.SECRET_KEY.
    """
    custom_key = settings.GMAIL_TOKEN_ENCRYPTION_KEY
    if custom_key:
        try:
            # Validate if it's already a valid 32-byte urlsafe base64 string
            raw = base64.urlsafe_b64decode(custom_key.encode("ascii"))
            if len(raw) == 32:
                return custom_key.encode("ascii")
        except Exception:
            logger.warning("Custom GMAIL_TOKEN_ENCRYPTION_KEY is invalid; deriving key from SECRET_KEY.")

    # Derive deterministic key from SECRET_KEY using SHA-256
    derived_32_bytes = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(derived_32_bytes)


def encrypt_token(plain_token: Optional[str]) -> Optional[str]:
    """Encrypts a sensitive OAuth token (refresh token or access token) at rest."""
    if not plain_token:
        return None
    try:
        fernet = Fernet(_get_encryption_key())
        encrypted_bytes = fernet.encrypt(plain_token.encode("utf-8"))
        return encrypted_bytes.decode("ascii")
    except Exception as e:
        logger.error(f"Failed to encrypt OAuth token: {e}")
        raise RuntimeError("Cryptographic token encryption failed") from e


def decrypt_token(encrypted_token: Optional[str]) -> Optional[str]:
    """Decrypts an encrypted OAuth token in memory."""
    if not encrypted_token:
        return None
    try:
        fernet = Fernet(_get_encryption_key())
        decrypted_bytes = fernet.decrypt(encrypted_token.encode("ascii"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt OAuth token: Invalid or corrupted token.")
        return None
    except Exception as e:
        logger.error(f"Failed to decrypt OAuth token: {e}")
        return None

