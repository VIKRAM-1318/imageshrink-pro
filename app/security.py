"""
ImageShrink Pro V2 Security & Authentication Module.
Provides secure password hashing (PBKDF2-HMAC-SHA256), session token management,
CSRF protection, rate limiting, and input sanitization.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security_bearer = HTTPBearer(auto_error=False)


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Enforces strong password policy for administrator accounts:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one numeric digit
    - At least one special symbol
    """
    if len(password) < 12:
        return False, "Password must be at least 12 characters in length."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]", password):
        return False, "Password must contain at least one special character."
    return True, "Password meets security requirements."


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 210,000 iterations and a 16-byte random salt."""
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210000)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    key_b64 = base64.b64encode(key).decode("ascii")
    return f"pbkdf2_sha256$210000${salt_b64}${key_b64}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored PBKDF2 hash using timing-safe comparison."""
    try:
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2].encode("ascii"))
        expected_key = base64.b64decode(parts[3].encode("ascii"))
        computed_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(expected_key, computed_key)
    except Exception:
        return False


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a high-entropy URL-safe cryptographic token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Hash a raw token before storing in database (never store raw session tokens)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_csrf_token(session_id: str) -> str:
    """Create a stateless CSRF token tied to a session ID using HMAC-SHA256."""
    raw = f"{session_id}:{settings.ADMIN_SECRET_KEY}".encode("utf-8")
    return hmac.new(settings.ADMIN_SECRET_KEY.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def verify_csrf_token(session_id: str, csrf_token: str) -> bool:
    """Verify CSRF token against expected HMAC using constant-time comparison."""
    if not session_id or not csrf_token:
        return False
    expected = create_csrf_token(session_id)
    return hmac.compare_digest(expected, csrf_token)


def create_access_token(data: Dict[str, Any], expires_delta_seconds: Optional[int] = None) -> str:
    """Generate an HMAC-SHA256 signed JWT token."""
    header = {"alg": "HS256", "typ": "JWT"}
    exp = int(time.time()) + (expires_delta_seconds or (settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60))
    payload = {**data, "exp": exp, "iat": int(time.time()), "iss": "imageshrink-pro"}

    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(settings.SECRET_KEY.encode(), signature_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify an HMAC-SHA256 signed JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signature_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(settings.SECRET_KEY.encode(), signature_input, hashlib.sha256).digest()
        
        sig_padding = "=" * (-len(sig_b64) % 4)
        actual_sig = base64.urlsafe_b64decode(sig_b64 + sig_padding)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_padding = "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + payload_padding)
        payload = json.loads(payload_bytes.decode())
        
        if payload.get("exp") and payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


def sanitize_filename(filename: str) -> str:
    """Strip dangerous characters and path traversals."""
    name = re.sub(r"[\\/]+", "", filename)
    name = re.sub(r"[^\w\.\-\s\(\)\[\]]", "", name)
    return name.strip()[:180] or "unnamed_image"


# In-memory sliding window rate limiter
_rate_limits: Dict[str, list[float]] = {}


def check_rate_limit(key: str, max_requests: int = 120, window_seconds: int = 60) -> bool:
    """Sliding-window in-memory rate limiter per IP or user key."""
    now = time.time()
    timestamps = _rate_limits.setdefault(key, [])
    cutoff = now - window_seconds
    _rate_limits[key] = [t for t in timestamps if t > cutoff]
    if len(_rate_limits[key]) >= max_requests:
        return False
    _rate_limits[key].append(now)
    return True


# Dedicated failed login attempts tracker
_failed_login_records: Dict[str, list[float]] = {}


def record_failed_login(identifier: str) -> int:
    """Record a failed login timestamp and return current count in 15 minute window."""
    now = time.time()
    attempts = _failed_login_records.setdefault(identifier, [])
    cutoff = now - (settings.ADMIN_LOCKOUT_MINUTES * 60)
    attempts = [t for t in attempts if t > cutoff]
    attempts.append(now)
    _failed_login_records[identifier] = attempts
    return len(attempts)


def clear_failed_logins(identifier: str) -> None:
    """Reset failed attempts upon successful authentication."""
    _failed_login_records.pop(identifier, None)


def is_login_rate_limited(identifier: str) -> Tuple[bool, int]:
    """Check if identifier (IP or username) is rate-limited. Returns (is_limited, remaining_seconds)."""
    now = time.time()
    attempts = _failed_login_records.get(identifier, [])
    cutoff = now - (settings.ADMIN_LOCKOUT_MINUTES * 60)
    recent = [t for t in attempts if t > cutoff]
    _failed_login_records[identifier] = recent
    if len(recent) >= settings.ADMIN_MAX_LOGIN_ATTEMPTS:
        earliest = min(recent)
        remaining = int((earliest + (settings.ADMIN_LOCKOUT_MINUTES * 60)) - now)
        return True, max(1, remaining)
    return False, 0
