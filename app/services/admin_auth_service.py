"""
Dedicated Administrator Authentication and Access Control Service.
Implements multi-layered security controls:
- Account lockout after repeated failed attempts
- Timing-safe password verification
- Server-side session storage with hashed tokens
- Cryptographic CSRF tokens
- Audit logging without password/credential exposure
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.database import db_session
from app.security import (
    clear_failed_logins,
    create_csrf_token,
    generate_secure_token,
    hash_password,
    hash_token,
    is_login_rate_limited,
    record_failed_login,
    validate_password_strength,
    verify_csrf_token,
    verify_password,
)

logger = logging.getLogger("imageshrink.admin_auth")


class AdminAuthService:

    @staticmethod
    def log_audit(
        action: str,
        status: str,
        admin_id: Optional[str] = None,
        username: Optional[str] = None,
        email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """
        Record tamper-evident audit logs.
        Strictly sanitizes details to NEVER include passwords or raw authentication tokens.
        Supports passing an active database connection to prevent nested transaction locks.
        """
        sanitized_details = {}
        if details:
            for k, v in details.items():
                if any(sens in k.lower() for sens in ("pass", "token", "secret", "cookie", "key", "auth")):
                    sanitized_details[k] = "[REDACTED]"
                else:
                    sanitized_details[k] = v

        stmt = """
        INSERT INTO admin_audit_logs
        (id, admin_id, admin_username, admin_email, action, ip_address, user_agent, status, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            str(uuid.uuid4()),
            admin_id,
            username,
            email,
            action,
            ip_address or "UNKNOWN",
            (user_agent or "")[:255],
            status,
            json.dumps(sanitized_details),
            time.time(),
        )

        try:
            if conn is not None:
                conn.execute(stmt, params)
            else:
                with db_session() as active_conn:
                    active_conn.execute(stmt, params)
        except Exception as exc:
            logger.error(f"Failed to record admin audit log: {exc}")

    @classmethod
    def authenticate(
        cls,
        identifier: str,
        password: str,
        ip_address: str,
        user_agent: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str], Optional[str]]:
        """
        Authenticate administrator.
        Returns (admin_user_dict, raw_session_token, csrf_token, error_message).
        """
        identifier_clean = identifier.strip().lower()
        now = time.time()

        # 1. Check IP-based rate limiting
        ip_limited, ip_rem = is_login_rate_limited(f"ip:{ip_address}")
        if ip_limited:
            cls.log_audit(
                action="LOGIN_BLOCKED_RATE_LIMIT",
                status="WARNING",
                username=identifier_clean,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "Excessive login requests from this IP", "remaining_seconds": ip_rem},
            )
            return None, None, None, f"Too many login attempts. Please wait {ip_rem} seconds before retrying."

        # 2. Check identifier-based rate limiting
        user_limited, user_rem = is_login_rate_limited(f"user:{identifier_clean}")
        if user_limited:
            cls.log_audit(
                action="LOGIN_BLOCKED_RATE_LIMIT",
                status="WARNING",
                username=identifier_clean,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "Excessive login requests for this username", "remaining_seconds": user_rem},
            )
            return None, None, None, f"Account temporarily locked due to failed attempts. Try again in {user_rem} seconds."

        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, username, email, hashed_password, role, status, failed_login_attempts, locked_until, password_updated_date
                FROM admin_users
                WHERE LOWER(email) = ? OR LOWER(username) = ?
                """,
                (identifier_clean, identifier_clean),
            )
            admin = cur.fetchone()

            # User not found
            if not admin:
                record_failed_login(f"ip:{ip_address}")
                record_failed_login(f"user:{identifier_clean}")
                cls.log_audit(
                    action="LOGIN_FAILURE",
                    status="FAILURE",
                    username=identifier_clean,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"reason": "User not found"},
                    conn=conn,
                )
                return None, None, None, "Invalid administrator credentials."

            admin_dict = dict(admin)
            admin_id = admin_dict["id"]

            # 3. Check Account Lockout State
            if admin_dict.get("locked_until") and admin_dict["locked_until"] > now:
                remaining_lock = int(admin_dict["locked_until"] - now)
                cls.log_audit(
                    action="LOGIN_ATTEMPT_LOCKED_ACCOUNT",
                    status="WARNING",
                    admin_id=admin_id,
                    username=admin_dict["username"],
                    email=admin_dict["email"],
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"remaining_seconds": remaining_lock},
                    conn=conn,
                )
                return None, None, None, f"Administrator account is locked. Please try again in {remaining_lock} seconds."

            # Check Suspended Account
            if admin_dict.get("status") == "suspended":
                cls.log_audit(
                    action="LOGIN_ATTEMPT_SUSPENDED_ACCOUNT",
                    status="WARNING",
                    admin_id=admin_id,
                    username=admin_dict["username"],
                    email=admin_dict["email"],
                    ip_address=ip_address,
                    user_agent=user_agent,
                    conn=conn,
                )
                return None, None, None, "Administrator account has been suspended by an owner."

            # 4. Verify Password
            if not verify_password(password, admin_dict["hashed_password"]):
                new_fails = admin_dict["failed_login_attempts"] + 1
                record_failed_login(f"ip:{ip_address}")
                record_failed_login(f"user:{identifier_clean}")

                if new_fails >= settings.ADMIN_MAX_LOGIN_ATTEMPTS:
                    lock_time = now + (settings.ADMIN_LOCKOUT_MINUTES * 60)
                    conn.execute(
                        "UPDATE admin_users SET failed_login_attempts = ?, locked_until = ?, status = 'locked', updated_at = ? WHERE id = ?",
                        (new_fails, lock_time, now, admin_id),
                    )
                    cls.log_audit(
                        action="ACCOUNT_LOCKOUT_TRIGGERED",
                        status="WARNING",
                        admin_id=admin_id,
                        username=admin_dict["username"],
                        email=admin_dict["email"],
                        ip_address=ip_address,
                        user_agent=user_agent,
                        details={"failed_attempts": new_fails, "lockout_duration_minutes": settings.ADMIN_LOCKOUT_MINUTES},
                        conn=conn,
                    )
                    return None, None, None, f"Too many incorrect attempts. Account locked for {settings.ADMIN_LOCKOUT_MINUTES} minutes."
                else:
                    conn.execute(
                        "UPDATE admin_users SET failed_login_attempts = ?, updated_at = ? WHERE id = ?",
                        (new_fails, now, admin_id),
                    )
                    cls.log_audit(
                        action="LOGIN_FAILURE",
                        status="FAILURE",
                        admin_id=admin_id,
                        username=admin_dict["username"],
                        email=admin_dict["email"],
                        ip_address=ip_address,
                        user_agent=user_agent,
                        details={"failed_attempt_count": new_fails},
                        conn=conn,
                    )
                    return None, None, None, "Invalid administrator credentials."

            # 5. Success: Reset failed counters, issue secure session
            clear_failed_logins(f"ip:{ip_address}")
            clear_failed_logins(f"user:{identifier_clean}")

            conn.execute(
                """
                UPDATE admin_users
                SET failed_login_attempts = 0, locked_until = NULL, status = 'active',
                    last_login = ?, last_login_ip = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, ip_address, now, admin_id),
            )

            # Generate Session
            raw_session_token = generate_secure_token(32)
            session_id = str(uuid.uuid4())
            csrf_token = create_csrf_token(session_id)
            expires_at = now + (settings.ADMIN_SESSION_EXPIRE_HOURS * 3600)

            conn.execute(
                """
                INSERT INTO admin_sessions
                (id, admin_id, token_hash, csrf_token, ip_address, user_agent, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    admin_id,
                    hash_token(raw_session_token),
                    csrf_token,
                    ip_address,
                    (user_agent or "")[:255],
                    expires_at,
                    now,
                ),
            )

            cls.log_audit(
                action="LOGIN_SUCCESS",
                status="SUCCESS",
                admin_id=admin_id,
                username=admin_dict["username"],
                email=admin_dict["email"],
                ip_address=ip_address,
                user_agent=user_agent,
                conn=conn,
            )

            admin_dict.pop("hashed_password", None)
            return admin_dict, raw_session_token, csrf_token, None

    @classmethod
    def get_admin_by_session(cls, raw_session_token: str) -> Optional[Dict[str, Any]]:
        """Validate session token and return admin user context."""
        if not raw_session_token:
            return None

        now = time.time()
        token_hashed = hash_token(raw_session_token)

        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 
                    s.id as session_id,
                    s.csrf_token,
                    s.expires_at,
                    u.id as admin_id,
                    u.username,
                    u.email,
                    u.role,
                    u.status,
                    u.password_updated_date,
                    u.last_login
                FROM admin_sessions s
                JOIN admin_users u ON s.admin_id = u.id
                WHERE s.token_hash = ? AND s.expires_at > ?
                """,
                (token_hashed, now),
            )
            row = cur.fetchone()
            if not row:
                return None

            data = dict(row)
            if data["status"] != "active":
                return None

            return data

    @classmethod
    def invalidate_session(cls, raw_session_token: str, ip_address: Optional[str] = None) -> None:
        """Log out administrator and invalidate session in database."""
        if not raw_session_token:
            return

        token_hashed = hash_token(raw_session_token)
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT s.admin_id, u.username, u.email
                FROM admin_sessions s
                JOIN admin_users u ON s.admin_id = u.id
                WHERE s.token_hash = ?
                """,
                (token_hashed,),
            )
            sess = cur.fetchone()
            if sess:
                cls.log_audit(
                    action="LOGOUT",
                    status="SUCCESS",
                    admin_id=sess["admin_id"],
                    username=sess["username"],
                    email=sess["email"],
                    ip_address=ip_address,
                    conn=conn,
                )

            conn.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hashed,))

    @classmethod
    def change_password(
        cls,
        admin_id: str,
        current_password: str,
        new_password: str,
        ip_address: str,
        user_agent: str,
    ) -> Tuple[bool, str]:
        """Change administrator password with verification and session termination."""
        valid, msg = validate_password_strength(new_password)
        if not valid:
            return False, msg

        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, username, email, hashed_password FROM admin_users WHERE id = ?", (admin_id,))
            admin = cur.fetchone()
            if not admin:
                return False, "Administrator account not found."

            if not verify_password(current_password, admin["hashed_password"]):
                cls.log_audit(
                    action="PASSWORD_CHANGE_FAILED_CURRENT_MISMATCH",
                    status="WARNING",
                    admin_id=admin_id,
                    username=admin["username"],
                    email=admin["email"],
                    ip_address=ip_address,
                    user_agent=user_agent,
                    conn=conn,
                )
                return False, "Current password verification failed."

            now = time.time()
            new_hash = hash_password(new_password)
            conn.execute(
                "UPDATE admin_users SET hashed_password = ?, password_updated_date = ?, updated_at = ? WHERE id = ?",
                (new_hash, now, now, admin_id),
            )

            conn.execute("DELETE FROM admin_sessions WHERE admin_id = ?", (admin_id,))

            cls.log_audit(
                action="PASSWORD_CHANGE_SUCCESS",
                status="SUCCESS",
                admin_id=admin_id,
                username=admin["username"],
                email=admin["email"],
                ip_address=ip_address,
                user_agent=user_agent,
                conn=conn,
            )

            return True, "Password updated successfully. All other sessions have been terminated."

    @staticmethod
    def get_audit_logs(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieve recent admin audit logs."""
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, admin_id, admin_username, admin_email, action, ip_address, user_agent, status, details_json, created_at
                FROM admin_audit_logs
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            return [dict(r) for r in cur.fetchall()]


admin_auth_service = AdminAuthService()
