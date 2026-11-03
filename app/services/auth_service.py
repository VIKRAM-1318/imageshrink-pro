"""
ImageShrink Pro V2 Authentication & User Management Service.
Handles:
- User Registration with password strength, confirmation, and terms acceptance
- Email verification via token and 6-digit OTP
- Secure login with brute-force lockout protection and new-device detection
- Password recovery (forgot & reset password)
- Authenticated profile updates, password change, and email change
- Session management & multi-device logout
- Account deletion
All transactional emails dispatched exclusively through Google Gmail API.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import secrets
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from app.config import settings
from app.database import db_session
from app.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from app.services.gmail_service import gmail_service

logger = logging.getLogger("imageshrink.auth")


class AuthService:
    # =========================================================================
    # 1. Registration
    # =========================================================================

    @staticmethod
    def register_user(
        email: str,
        password: str,
        confirm_password: str,
        full_name: str = "",
        terms_accepted: bool = False,
        privacy_accepted: bool = False,
        client_ip: str = "127.0.0.1",
        user_agent: str = "Unknown",
    ) -> Dict[str, Any]:
        """Creates a new user account with unverified status and assigns the Free subscription tier."""
        clean_email = email.strip().lower()

        # Validation
        if not terms_accepted:
            raise HTTPException(status_code=400, detail="You must accept the Terms of Service to create an account.")
        if not privacy_accepted:
            raise HTTPException(status_code=400, detail="You must accept the Privacy Policy to create an account.")
        if password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match.")

        # Password strength validation
        valid, msg = validate_password_strength(password)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)

        now = time.time()
        user_id = str(uuid.uuid4())

        with db_session() as conn:
            cur = conn.cursor()
            # Check for duplicate email
            cur.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="An account with this email address already exists.")

            hashed_pwd = hash_password(password)

            # Insert user (unverified by default)
            cur.execute(
                """
                INSERT INTO users (
                    id, email, hashed_password, full_name, plan, is_active,
                    is_verified, failed_login_attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'free', 1, 0, 0, ?, ?)
                """,
                (user_id, clean_email, hashed_pwd, full_name.strip(), now, now),
            )

            # Automatically provision Free Subscription (50 ops/month)
            free_limits = settings.PLANS["free"]
            sub_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO subscriptions (
                    id, user_id, plan, status, billing_cycle, monthly_allowance,
                    used_quota, current_period_start, current_period_end,
                    cancel_at_period_end, provider, created_at, updated_at
                ) VALUES (?, ?, 'free', 'active', 'monthly', ?, 0, ?, ?, 0, 'system', ?, ?)
                """,
                (sub_id, user_id, free_limits.monthly_allowance, now, now + 30 * 86400, now, now),
            )

            # Generate Verification Token & 6-digit OTP
            raw_token = generate_secure_token(32)
            token_hashed = hash_token(raw_token)
            otp_code = f"{random.randint(100000, 999999)}"
            token_id = str(uuid.uuid4())
            token_expires = now + 24 * 3600  # 24 hours

            cur.execute(
                """
                INSERT INTO email_verification_tokens (
                    id, user_id, email, token_hash, otp_code, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (token_id, user_id, clean_email, token_hashed, otp_code, token_expires, now),
            )

            # Log registration security event
            cur.execute(
                """
                INSERT INTO user_security_events (
                    id, user_id, event_type, ip_address, user_agent, details_json, created_at
                ) VALUES (?, ?, 'account_registered', ?, ?, '{}', ?)
                """,
                (str(uuid.uuid4()), user_id, client_ip, user_agent, now),
            )

        # Send Transactional Emails via Google Gmail API
        try:
            # 1. Registration Confirmation
            gmail_service.send_account_registration(full_name=full_name, email=clean_email)
            # 2. Email Verification with OTP & Link
            gmail_service.send_email_verification(
                full_name=full_name,
                email=clean_email,
                token=raw_token,
                otp_code=otp_code,
            )
        except Exception as e:
            logger.error(f"Failed to dispatch initial registration emails via Gmail: {e}")

        # Issue access token so user is authenticated immediately
        token = create_access_token({"sub": user_id, "email": clean_email, "plan": "free", "is_verified": False})

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "email": clean_email,
                "full_name": full_name.strip(),
                "plan": "free",
                "is_verified": False,
            },
            "message": "Registration successful! A verification link and 6-digit code have been sent to your email.",
        }

    # =========================================================================
    # 2. Email Verification
    # =========================================================================

    @staticmethod
    def verify_email(
        token: Optional[str] = None,
        email: Optional[str] = None,
        otp_code: Optional[str] = None,
        client_ip: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Verifies an account using either the cryptographic URL token or 6-digit OTP code."""
        now = time.time()
        with db_session() as conn:
            cur = conn.cursor()

            row = None
            if token:
                token_hashed = hash_token(token.strip())
                cur.execute(
                    """
                    SELECT id, user_id, email, expires_at, used_at
                    FROM email_verification_tokens
                    WHERE token_hash = ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (token_hashed,),
                )
                row = cur.fetchone()
            elif email and otp_code:
                clean_email = email.strip().lower()
                clean_otp = otp_code.strip()
                cur.execute(
                    """
                    SELECT id, user_id, email, expires_at, used_at
                    FROM email_verification_tokens
                    WHERE email = ? AND otp_code = ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (clean_email, clean_otp),
                )
                row = cur.fetchone()
            else:
                raise HTTPException(status_code=400, detail="Verification token or OTP code is required.")

            if not row:
                raise HTTPException(status_code=400, detail="Invalid verification code or link.")

            if row["used_at"] is not None:
                raise HTTPException(status_code=400, detail="This verification token has already been used.")

            if now > row["expires_at"]:
                raise HTTPException(status_code=400, detail="This verification token has expired. Please request a new one.")

            user_id = row["user_id"]
            token_id = row["id"]

            # Mark token as used
            cur.execute("UPDATE email_verification_tokens SET used_at = ? WHERE id = ?", (now, token_id))

            # Mark user as verified
            cur.execute(
                """
                UPDATE users
                SET is_verified = 1, email_verified_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, user_id),
            )

            # Security audit event
            cur.execute(
                """
                INSERT INTO user_security_events (
                    id, user_id, event_type, ip_address, details_json, created_at
                ) VALUES (?, ?, 'email_verified', ?, '{}', ?)
                """,
                (str(uuid.uuid4()), user_id, client_ip, now),
            )

        logger.info(f"User {user_id} successfully verified email.")
        return {"success": True, "message": "Email address verified successfully!"}

    @staticmethod
    def resend_verification(email: str, client_ip: str = "127.0.0.1") -> Dict[str, Any]:
        """Generates a fresh verification token & OTP and sends it via Gmail."""
        clean_email = email.strip().lower()
        now = time.time()

        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, full_name, is_verified FROM users WHERE email = ?", (clean_email,))
            user = cur.fetchone()
            if not user:
                # Do not reveal whether account exists
                return {"success": True, "message": "If this email is registered, a new verification link has been sent."}

            if user["is_verified"]:
                return {"success": True, "message": "This email address is already verified."}

            # Rate limit resends: 1 request per 60 seconds
            cur.execute(
                "SELECT created_at FROM email_verification_tokens WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user["id"],),
            )
            last_token = cur.fetchone()
            if last_token and (now - last_token["created_at"]) < 60:
                retry_after = int(60 - (now - last_token["created_at"]))
                raise HTTPException(
                    status_code=429,
                    detail=f"Please wait {retry_after} seconds before requesting another verification code.",
                )

            # Generate fresh token & OTP
            raw_token = generate_secure_token(32)
            token_hashed = hash_token(raw_token)
            otp_code = f"{random.randint(100000, 999999)}"
            token_id = str(uuid.uuid4())
            token_expires = now + 24 * 3600

            cur.execute(
                """
                INSERT INTO email_verification_tokens (
                    id, user_id, email, token_hash, otp_code, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (token_id, user["id"], clean_email, token_hashed, otp_code, token_expires, now),
            )

        # Dispatch via Gmail API
        gmail_service.send_email_verification(
            full_name=user["full_name"],
            email=clean_email,
            token=raw_token,
            otp_code=otp_code,
        )

        return {"success": True, "message": "Verification code and link resent successfully."}

    # =========================================================================
    # 3. Authentication & Login
    # =========================================================================

    @staticmethod
    def login_user(
        email: str,
        password: str,
        remember_me: bool = False,
        client_ip: str = "127.0.0.1",
        user_agent: str = "Unknown",
    ) -> Dict[str, Any]:
        """
        Authenticates user with password verification, brute-force lockout protection,
        session tracking, and new-device detection.
        """
        clean_email = email.strip().lower()
        now = time.time()

        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, email, hashed_password, full_name, plan, is_active,
                       is_verified, failed_login_attempts, locked_until
                FROM users
                WHERE email = ?
                """,
                (clean_email,),
            )
            user = cur.fetchone()

            # Account Lockout Check
            if user and user["locked_until"] and user["locked_until"] > now:
                remaining_lock = int(user["locked_until"] - now)
                # Log lockout hit
                cur.execute(
                    """
                    INSERT INTO login_activity (id, user_id, email, ip_address, user_agent, status, failure_reason, created_at)
                    VALUES (?, ?, ?, ?, ?, 'locked', 'Account locked due to repeated failures', ?)
                    """,
                    (str(uuid.uuid4()), user["id"], clean_email, client_ip, user_agent, now),
                )
                conn.commit()
                raise HTTPException(
                    status_code=403,
                    detail=f"Account temporarily locked due to repeated failed login attempts. Please wait {remaining_lock // 60 + 1} minutes or reset your password.",
                )

            # Credential check
            if not user or not verify_password(password, user["hashed_password"]):
                should_alert = False
                if user:
                    new_fails = user["failed_login_attempts"] + 1
                    lock_time = None
                    if new_fails >= 5:
                        lock_time = now + 15 * 60  # 15 minutes lockout
                        should_alert = True

                    cur.execute(
                        "UPDATE users SET failed_login_attempts = ?, locked_until = ?, updated_at = ? WHERE id = ?",
                        (new_fails, lock_time, now, user["id"]),
                    )

                # Log failure
                cur.execute(
                    """
                    INSERT INTO login_activity (id, user_id, email, ip_address, user_agent, status, failure_reason, created_at)
                    VALUES (?, ?, ?, ?, ?, 'failed', 'Invalid password or user not found', ?)
                    """,
                    (str(uuid.uuid4()), user["id"] if user else None, clean_email, client_ip, user_agent, now),
                )
                conn.commit()

                if should_alert and user:
                    try:
                        gmail_service.send_suspicious_login_alert(
                            full_name=user["full_name"],
                            email=clean_email,
                            ip_address=client_ip,
                            reason="5 consecutive failed password attempts",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send suspicious login alert: {e}")

                raise HTTPException(status_code=401, detail="Invalid email or password.")

            if not user["is_active"]:
                raise HTTPException(status_code=403, detail="Account is suspended. Please contact support.")

            user_id = user["id"]

            # Reset failed login count on successful auth
            cur.execute(
                """
                UPDATE users
                SET failed_login_attempts = 0, locked_until = NULL, last_login = ?, last_login_ip = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, client_ip, now, user_id),
            )

            # Check if new device / browser (device detection)
            cur.execute(
                """
                SELECT id FROM login_activity
                WHERE user_id = ? AND status = 'success' AND ip_address = ?
                LIMIT 1
                """,
                (user_id, client_ip),
            )
            is_known_device = cur.fetchone() is not None

            # Log successful login
            cur.execute(
                """
                INSERT INTO login_activity (id, user_id, email, ip_address, user_agent, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'success', ?)
                """,
                (str(uuid.uuid4()), user_id, clean_email, client_ip, user_agent, now),
            )

            # Create User Session
            session_duration = 30 * 86400 if remember_me else 24 * 3600
            session_id = str(uuid.uuid4())
            session_token = generate_secure_token(32)
            session_token_hash = hash_token(session_token)

            cur.execute(
                """
                INSERT INTO user_sessions (
                    id, user_id, token_hash, ip_address, user_agent,
                    expires_at, is_remembered, last_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    session_token_hash,
                    client_ip,
                    user_agent,
                    now + session_duration,
                    1 if remember_me else 0,
                    now,
                    now,
                ),
            )

        # Trigger new device alert if unrecognized IP
        if not is_known_device:
            try:
                gmail_service.send_new_device_login(
                    full_name=user["full_name"],
                    email=clean_email,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
            except Exception as e:
                logger.error(f"Failed to send new device login email: {e}")

        # Create JWT access token
        access_token = create_access_token(
            {
                "sub": user_id,
                "email": clean_email,
                "plan": user["plan"],
                "is_verified": bool(user["is_verified"]),
                "session_id": session_id,
            },
            expires_delta_seconds=session_duration,
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "session_id": session_id,
            "user": {
                "id": user_id,
                "email": clean_email,
                "full_name": user["full_name"],
                "plan": user["plan"],
                "is_verified": bool(user["is_verified"]),
            },
        }

    # =========================================================================
    # 4. Password Recovery (Forgot & Reset)
    # =========================================================================

    @staticmethod
    def forgot_password(email: str, client_ip: str = "127.0.0.1") -> Dict[str, Any]:
        """Initiates password reset link dispatch via Gmail."""
        clean_email = email.strip().lower()
        now = time.time()
        reset_info = None

        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, full_name, is_active FROM users WHERE email = ?", (clean_email,))
            user = cur.fetchone()

            if user and user["is_active"]:
                # Rate limit password reset requests: max 3 requests per hour
                cur.execute(
                    "SELECT COUNT(*) as count FROM password_reset_tokens WHERE user_id = ? AND created_at >= ?",
                    (user["id"], now - 3600),
                )
                recent_count = cur.fetchone()["count"]
                if recent_count >= 3:
                    # Generic success response to avoid leaking rate limit or existence
                    return {"success": True, "message": "If an account exists with this email, a password reset link has been sent."}

                # Generate secure reset token
                raw_token = generate_secure_token(32)
                token_hash = hash_token(raw_token)
                token_id = str(uuid.uuid4())
                expires_at = now + 3600  # 1 hour expiration

                cur.execute(
                    """
                    INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (token_id, user["id"], token_hash, expires_at, now),
                )
                reset_info = (user["full_name"], raw_token)

        # Send via Gmail API outside database transaction
        if reset_info:
            full_name, raw_token = reset_info
            try:
                gmail_service.send_password_reset(
                    full_name=full_name,
                    email=clean_email,
                    token=raw_token,
                )
            except Exception as e:
                logger.error(f"Failed to dispatch password reset email via Gmail: {e}")

        # Always return generic message to prevent account enumeration
        return {"success": True, "message": "If an account exists with this email address, a password reset link has been sent."}

    @staticmethod
    def reset_password(
        token: str,
        new_password: str,
        confirm_password: str,
        client_ip: str = "127.0.0.1",
        user_agent: str = "Unknown",
    ) -> Dict[str, Any]:
        """Resets user password with token invalidation and terminates active sessions."""
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match.")

        valid, msg = validate_password_strength(new_password)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)

        now = time.time()
        token_hash = hash_token(token.strip())

        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, user_id, expires_at, used_at
                FROM password_reset_tokens
                WHERE token_hash = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="Invalid password reset link.")

            if row["used_at"] is not None:
                raise HTTPException(status_code=400, detail="This password reset link has already been used.")

            if now > row["expires_at"]:
                raise HTTPException(status_code=400, detail="This password reset link has expired. Please request a new one.")

            user_id = row["user_id"]
            token_id = row["id"]

            # Update password
            hashed_pwd = hash_password(new_password)
            cur.execute(
                "UPDATE users SET hashed_password = ?, failed_login_attempts = 0, locked_until = NULL, updated_at = ? WHERE id = ?",
                (hashed_pwd, now, user_id),
            )

            # Invalidate reset token
            cur.execute("UPDATE password_reset_tokens SET used_at = ? WHERE id = ?", (now, token_id))

            # Invalidate all active user sessions across all devices
            cur.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))

            # Fetch user email for notification
            cur.execute("SELECT email, full_name FROM users WHERE id = ?", (user_id,))
            user_data = cur.fetchone()

            # Log security event
            cur.execute(
                """
                INSERT INTO user_security_events (id, user_id, event_type, ip_address, user_agent, details_json, created_at)
                VALUES (?, ?, 'password_reset_completed', ?, ?, '{}', ?)
                """,
                (str(uuid.uuid4()), user_id, client_ip, user_agent, now),
            )

        # Dispatch Password Changed Confirmation Email via Gmail API
        if user_data:
            try:
                gmail_service.send_password_changed(
                    full_name=user_data["full_name"],
                    email=user_data["email"],
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
            except Exception as e:
                logger.error(f"Failed to send password changed email: {e}")

        return {"success": True, "message": "Password reset successfully. You can now sign in with your new password."}

    # =========================================================================
    # 5. Authenticated Profile & Security Settings
    # =========================================================================

    @staticmethod
    def change_password(
        user_id: str,
        current_password: str,
        new_password: str,
        confirm_password: str,
        client_ip: str = "127.0.0.1",
        user_agent: str = "Unknown",
        current_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Changes password for authenticated user and invalidates other sessions."""
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="New passwords do not match.")

        valid, msg = validate_password_strength(new_password)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)

        now = time.time()
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, email, full_name, hashed_password FROM users WHERE id = ?", (user_id,))
            user = cur.fetchone()
            if not user or not verify_password(current_password, user["hashed_password"]):
                raise HTTPException(status_code=400, detail="Current password is incorrect.")

            hashed_pwd = hash_password(new_password)
            cur.execute("UPDATE users SET hashed_password = ?, updated_at = ? WHERE id = ?", (hashed_pwd, now, user_id))

            # Invalidate all other sessions except current session
            if current_session_id:
                cur.execute("DELETE FROM user_sessions WHERE user_id = ? AND id != ?", (user_id, current_session_id))
            else:
                cur.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))

            # Log security event
            cur.execute(
                """
                INSERT INTO user_security_events (id, user_id, event_type, ip_address, user_agent, details_json, created_at)
                VALUES (?, ?, 'password_changed', ?, ?, '{}', ?)
                """,
                (str(uuid.uuid4()), user_id, client_ip, user_agent, now),
            )

        # Send confirmation email
        try:
            gmail_service.send_password_changed(
                full_name=user["full_name"],
                email=user["email"],
                ip_address=client_ip,
                user_agent=user_agent,
            )
        except Exception as e:
            logger.error(f"Failed to send password changed email: {e}")

        return {"success": True, "message": "Password updated successfully. Other device sessions have been revoked."}

    @staticmethod
    def update_profile(user_id: str, full_name: str) -> Dict[str, Any]:
        """Updates full name on user profile."""
        now = time.time()
        clean_name = full_name.strip()
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET full_name = ?, updated_at = ? WHERE id = ?", (clean_name, now, user_id))
            cur.execute("SELECT id, email, full_name, plan, is_verified, created_at FROM users WHERE id = ?", (user_id,))
            user = cur.fetchone()
        return {"success": True, "user": dict(user)}

    @staticmethod
    def get_profile_and_security_overview(user_id: str) -> Dict[str, Any]:
        """Returns comprehensive user profile, subscription, active sessions, and security events."""
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, email, full_name, plan, is_verified, email_verified_at,
                       last_login, last_login_ip, created_at
                FROM users WHERE id = ?
                """,
                (user_id,),
            )
            user_row = cur.fetchone()
            if not user_row:
                raise HTTPException(status_code=404, detail="User not found.")

            # Active Sessions
            cur.execute(
                """
                SELECT id, ip_address, user_agent, is_remembered, last_active, created_at
                FROM user_sessions
                WHERE user_id = ? AND expires_at > ?
                ORDER BY last_active DESC
                """,
                (user_id, time.time()),
            )
            sessions = [dict(s) for s in cur.fetchall()]

            # Security Events
            cur.execute(
                """
                SELECT event_type, ip_address, created_at
                FROM user_security_events
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (user_id,),
            )
            security_events = [dict(e) for e in cur.fetchall()]

        return {
            "profile": dict(user_row),
            "sessions": sessions,
            "security_events": security_events,
        }

    @staticmethod
    def revoke_session(user_id: str, session_id: str) -> Dict[str, Any]:
        """Revokes a specific session."""
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM user_sessions WHERE user_id = ? AND id = ?", (user_id, session_id))
        return {"success": True, "message": "Session revoked."}

    @staticmethod
    def logout_all_sessions(user_id: str) -> Dict[str, Any]:
        """Terminates all active sessions for the user across all devices."""
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        return {"success": True, "message": "Logged out from all devices."}

    @staticmethod
    def delete_account(user_id: str, password: str) -> Dict[str, Any]:
        """Permanently deletes user account, cancels subscriptions, and purges data."""
        now = time.time()
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT email, full_name, hashed_password FROM users WHERE id = ?", (user_id,))
            user = cur.fetchone()
            if not user or not verify_password(password, user["hashed_password"]):
                raise HTTPException(status_code=400, detail="Incorrect password. Account deletion aborted.")

            # Delete subscriptions, sessions, tokens, and user profile (cascade)
            cur.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM email_verification_tokens WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))

        # Send deletion confirmation via Gmail API
        try:
            gmail_service.send_account_deleted(full_name=user["full_name"], email=user["email"])
        except Exception as e:
            logger.error(f"Failed to send account deletion email: {e}")

        return {"success": True, "message": "Account successfully deleted."}


auth_service = AuthService()
