"""
FastAPI Dependencies for ImageShrink Pro V2.
Handles authentication token verification, user retrieval, admin authorization,
and per-endpoint rate limiting.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import db_session
from app.security import check_rate_limit, decode_access_token

security_scheme = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
) -> Optional[Dict[str, Any]]:
    """Retrieve user from JWT if token is provided, otherwise return None (guest user)."""
    if not credentials or not credentials.credentials:
        return None
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    user_id = payload["sub"]
    with db_session() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, email, full_name, plan, is_active FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        if not row or not row["is_active"]:
            return None
        return dict(row)


async def get_current_user(
    user: Optional[Dict[str, Any]] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """Require valid authenticated user."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided or have expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin_user(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Require administrator privileges."""
    if not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required for this resource.",
        )
    return user


def rate_limiter_dependency(max_requests: int = 150, window_seconds: int = 60):
    async def _rate_check(request: Request):
        client_ip = request.client.host if request.client else "127.0.0.1"
        if not check_rate_limit(client_ip, max_requests=max_requests, window_seconds=window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please wait before making additional requests.",
            )
    return _rate_check

