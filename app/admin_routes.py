"""
Private Administrator Routes and Access Control.
Provides isolated, protected administrative portal and APIs:
- Secure separate admin login with rate-limiting and lockout
- HTTP-only authentication session cookies with SameSite policy
- Anti-CSRF token verification on state-changing requests
- Real-time audit logging for all privileged actions
- Automatic redirection of unauthenticated requests
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.config import BASE_DIR, settings
from app.database import db_session
from app.security import verify_csrf_token
from app.services.admin_auth_service import admin_auth_service
from app.services.admin_service import admin_service

admin_router = APIRouter(prefix="/admin", tags=["admin"])


# -------------------------------------------------------------
# Dependency: Require Authenticated Admin Session
# -------------------------------------------------------------
async def get_current_admin_api(
    request: Request,
    isp_admin_session: Optional[str] = Cookie(None),
) -> Dict[str, Any]:
    """Dependency for Admin API endpoints: returns HTTP 401/403 on invalid session."""
    client_ip = request.client.host if request.client else "UNKNOWN"
    user_agent = request.headers.get("user-agent", "")

    if not isp_admin_session:
        admin_auth_service.log_audit(
            action="UNAUTHORIZED_API_ACCESS_ATTEMPT",
            status="WARNING",
            ip_address=client_ip,
            user_agent=user_agent,
            details={"path": request.url.path, "method": request.method},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrator authentication required.",
        )

    admin_ctx = admin_auth_service.get_admin_by_session(isp_admin_session)
    if not admin_ctx:
        admin_auth_service.log_audit(
            action="INVALID_SESSION_API_ACCESS_ATTEMPT",
            status="WARNING",
            ip_address=client_ip,
            user_agent=user_agent,
            details={"path": request.url.path},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again.",
        )

    return admin_ctx


async def verify_admin_csrf(
    request: Request,
    admin_ctx: Dict[str, Any] = Depends(get_current_admin_api),
    x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token"),
) -> None:
    """Validates anti-CSRF token on all state-changing admin actions."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        session_id = admin_ctx.get("session_id", "")
        if not x_csrf_token or not verify_csrf_token(session_id, x_csrf_token):
            admin_auth_service.log_audit(
                action="CSRF_VALIDATION_FAILED",
                status="WARNING",
                admin_id=admin_ctx.get("admin_id"),
                username=admin_ctx.get("username"),
                email=admin_ctx.get("email"),
                ip_address=request.client.host if request.client else "UNKNOWN",
                details={"path": request.url.path},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed. Refresh the page and try again.",
            )


# -------------------------------------------------------------
# Admin HTML Portal Views
# -------------------------------------------------------------
@admin_router.get("/login", response_class=HTMLResponse)
async def admin_login_view(
    request: Request,
    isp_admin_session: Optional[str] = Cookie(None),
):
    """Private administrator login page. Redirects to dashboard if already authenticated."""
    if isp_admin_session:
        admin_ctx = admin_auth_service.get_admin_by_session(isp_admin_session)
        if admin_ctx:
            return RedirectResponse(url="/admin", status_code=303)

    login_path = BASE_DIR / "app" / "templates" / "admin_login.html"
    if login_path.is_file():
        return login_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>Admin Login</h1>")


@admin_router.post("/login")
async def admin_login_action(
    request: Request,
    response: Response,
    identifier: str = Form(...),
    password: str = Form(...),
):
    """
    Processes administrator login.
    Enforces rate limits, temporary account lockouts, sets secure HTTP-only cookie.
    """
    client_ip = request.client.host if request.client else "UNKNOWN"
    user_agent = request.headers.get("user-agent", "")

    admin_user, raw_token, csrf_token, error_msg = admin_auth_service.authenticate(
        identifier=identifier,
        password=password,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    if error_msg:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": error_msg},
        )

    res = JSONResponse(
        content={
            "success": True,
            "message": "Authentication successful.",
            "redirect_url": "/admin",
            "csrf_token": csrf_token,
        }
    )

    # Issue HTTP-Only session cookie
    res.set_cookie(
        key=settings.ADMIN_SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=settings.ADMIN_SESSION_EXPIRE_HOURS * 3600,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/admin",
    )

    # Issue CSRF cookie (accessible to client-side scripts to attach to headers)
    res.set_cookie(
        key=settings.ADMIN_CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.ADMIN_SESSION_EXPIRE_HOURS * 3600,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/admin",
    )

    return res


@admin_router.post("/logout")
async def admin_logout_action(
    request: Request,
    response: Response,
    isp_admin_session: Optional[str] = Cookie(None),
):
    """Invalidates session in database and removes authentication cookies."""
    client_ip = request.client.host if request.client else "UNKNOWN"
    if isp_admin_session:
        admin_auth_service.invalidate_session(isp_admin_session, ip_address=client_ip)

    res = RedirectResponse(url="/admin/login", status_code=303)
    res.delete_cookie(settings.ADMIN_SESSION_COOKIE_NAME, path="/admin")
    res.delete_cookie(settings.ADMIN_CSRF_COOKIE_NAME, path="/admin")
    return res


@admin_router.get("", response_class=HTMLResponse)
@admin_router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard_view(
    request: Request,
    isp_admin_session: Optional[str] = Cookie(None),
):
    """
    Private administrator dashboard.
    Strictly checks session: unauthenticated visitors are redirected to /admin/login.
    """
    client_ip = request.client.host if request.client else "UNKNOWN"
    user_agent = request.headers.get("user-agent", "")

    if not isp_admin_session:
        admin_auth_service.log_audit(
            action="UNAUTHORIZED_DASHBOARD_ACCESS_ATTEMPT",
            status="WARNING",
            ip_address=client_ip,
            user_agent=user_agent,
        )
        return RedirectResponse(url="/admin/login", status_code=303)

    admin_ctx = admin_auth_service.get_admin_by_session(isp_admin_session)
    if not admin_ctx:
        return RedirectResponse(url="/admin/login", status_code=303)

    dash_path = BASE_DIR / "app" / "templates" / "admin_dashboard.html"
    if dash_path.is_file():
        content = dash_path.read_text(encoding="utf-8")
        # Injected session metadata (no secrets)
        content = content.replace("{{ADMIN_USERNAME}}", admin_ctx["username"])
        content = content.replace("{{ADMIN_EMAIL}}", admin_ctx["email"])
        content = content.replace("{{ADMIN_ROLE}}", admin_ctx["role"])
        content = content.replace("{{CSRF_TOKEN}}", admin_ctx["csrf_token"])
        return HTMLResponse(content)

    return HTMLResponse("<h1>Admin Dashboard</h1>")


# -------------------------------------------------------------
# Protected Admin APIs (Under /admin/api/...)
# -------------------------------------------------------------
@admin_router.get("/api/me")
async def admin_get_me(admin_ctx: Dict[str, Any] = Depends(get_current_admin_api)):
    """Returns authenticated administrator profile and current session info."""
    return {
        "id": admin_ctx["admin_id"],
        "username": admin_ctx["username"],
        "email": admin_ctx["email"],
        "role": admin_ctx["role"],
        "last_login": admin_ctx.get("last_login"),
        "password_updated_date": admin_ctx.get("password_updated_date"),
        "csrf_token": admin_ctx["csrf_token"],
    }


@admin_router.get("/api/overview")
async def admin_get_overview(admin_ctx: Dict[str, Any] = Depends(get_current_admin_api)):
    """Aggregated health, storage, and activity metrics."""
    return admin_service.get_system_health()


@admin_router.get("/api/users")
async def admin_get_users(
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    admin_ctx: Dict[str, Any] = Depends(get_current_admin_api),
):
    """Search and paginate registered users."""
    return admin_service.list_users(search=search, limit=limit, offset=offset)


class UpdateUserStatusSchema(BaseModel):
    is_active: bool
    plan: str


@admin_router.post("/api/users/{user_id}/status")
async def admin_update_user_status(
    user_id: str,
    payload: UpdateUserStatusSchema,
    request: Request,
    admin_ctx: Dict[str, Any] = Depends(get_current_admin_api),
    _csrf: None = Depends(verify_admin_csrf),
):
    """Suspend/activate user account or adjust plan."""
    success = admin_service.update_user_status(
        admin_email=admin_ctx["email"],
        user_id=user_id,
        is_active=payload.is_active,
        is_admin=False,
        plan=payload.plan,
    )
    if not success:
        raise HTTPException(status_code=404, detail="User account not found.")

    admin_auth_service.log_audit(
        action="USER_STATUS_UPDATED",
        status="SUCCESS",
        admin_id=admin_ctx["admin_id"],
        username=admin_ctx["username"],
        email=admin_ctx["email"],
        ip_address=request.client.host if request.client else "UNKNOWN",
        details={"target_user_id": user_id, "is_active": payload.is_active, "plan": payload.plan},
    )
    return {"success": True, "message": "User status updated successfully."}


@admin_router.get("/api/batches")
async def admin_get_batches(
    limit: int = 50,
    offset: int = 0,
    admin_ctx: Dict[str, Any] = Depends(get_current_admin_api),
):
    """Retrieve recent optimization batches across all users."""
    with db_session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, name, total_files, processed_files, failed_files,
                   total_original_size, total_optimized_size, status, mode, created_at, completed_at
            FROM upload_batches
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [dict(r) for r in cur.fetchall()]


@admin_router.delete("/api/batches/{batch_id}")
async def admin_delete_batch(
    batch_id: str,
    request: Request,
    admin_ctx: Dict[str, Any] = Depends(get_current_admin_api),
    _csrf: None = Depends(verify_admin_csrf),
):
    """Administrative deletion of batch records and temporary files."""
    with db_session() as conn:
        conn.execute("DELETE FROM upload_batches WHERE id = ?", (batch_id,))

    admin_auth_service.log_audit(
        action="BATCH_DELETED",
        status="SUCCESS",
        admin_id=admin_ctx["admin_id"],
        username=admin_ctx["username"],
        email=admin_ctx["email"],
        ip_address=request.client.host if request.client else "UNKNOWN",
        details={"batch_id": batch_id},
    )
    return {"success": True, "message": f"Batch {batch_id} removed by administrator."}


@admin_router.get("/api/logs")
async def admin_get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    admin_ctx: Dict[str, Any] = Depends(get_current_admin_api),
):
    """Access security audit log history."""
    return admin_auth_service.get_audit_logs(limit=limit, offset=offset)


class ChangePasswordSchema(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=12)


@admin_router.post("/api/change-password")
async def admin_change_password(
    payload: ChangePasswordSchema,
    request: Request,
    admin_ctx: Dict[str, Any] = Depends(get_current_admin_api),
    _csrf: None = Depends(verify_admin_csrf),
):
    """Secure password update for administrator."""
    client_ip = request.client.host if request.client else "UNKNOWN"
    user_agent = request.headers.get("user-agent", "")

    success, msg = admin_auth_service.change_password(
        admin_id=admin_ctx["admin_id"],
        current_password=payload.current_password,
        new_password=payload.new_password,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return {"success": True, "message": msg}

