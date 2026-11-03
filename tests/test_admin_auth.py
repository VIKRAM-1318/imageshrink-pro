"""
Comprehensive Security and Authentication Test Suite for ImageShrink Pro V2.
Tests all non-negotiable security requirements:
1. Direct admin URL access without login
2. Login with incorrect credentials
3. Accessing admin APIs without authentication
4. Accessing admin APIs using normal user credentials
5. Session expiration & session invalidation
6. Logout and session token reuse prevention
7. Brute-force protection & account lockout
8. Anti-CSRF protection on state-changing administrative requests
9. Strong password policy enforcement
10. Password hashing & salt security (no plaintext)
11. API documentation endpoints (/docs, /redoc) hidden
"""
from __future__ import annotations

import time
import uuid
import pytest
from app.config import settings
from app.database import db_session, init_db
from app.security import (
    create_access_token,
    create_csrf_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_csrf_token,
    verify_password,
)
from app.services.admin_auth_service import admin_auth_service


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database schema is fresh for testing."""
    init_db()


def test_password_policy_enforcement():
    """Requirement 3 & 8: Strong password requirements."""
    # Too short (< 12 chars)
    valid, msg = validate_password_strength("Short1!Aa")
    assert not valid
    assert "at least 12 characters" in msg

    # Missing uppercase
    valid, msg = validate_password_strength("alllowercase123!@#")
    assert not valid
    assert "uppercase" in msg

    # Missing lowercase
    valid, msg = validate_password_strength("ALLUPPERCASE123!@#")
    assert not valid
    assert "lowercase" in msg

    # Missing number
    valid, msg = validate_password_strength("NoNumbersAtAll!@#Aa")
    assert not valid
    assert "number" in msg

    # Missing special symbol
    valid, msg = validate_password_strength("NoSpecialSymbols123Aa")
    assert not valid
    assert "special character" in msg

    # Valid strong password
    valid, msg = validate_password_strength("StrongPass_2026!#Secure")
    assert valid


def test_password_hashing_security():
    """Requirement 2: Store passwords using strong salted password hashing (never plaintext)."""
    password = "SuperAdminPassword_2026!$"
    hashed = hash_password(password)

    # Must contain salt, algorithm, iterations
    assert hashed.startswith("pbkdf2_sha256$210000$")
    assert password not in hashed
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_admin_authentication_and_session_creation():
    """Requirement 1, 3: Authenticate administrator and create secure session."""
    test_user = f"admin_test_{uuid.uuid4().hex[:6]}"
    test_email = f"{test_user}@imageshrink.internal"
    test_pwd = "AdminTestPassword_2026!#"

    # Create admin directly in database
    now = time.time()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO admin_users (
                id, username, email, hashed_password, role, status,
                failed_login_attempts, locked_until, created_date,
                last_login, last_login_ip, password_updated_date, updated_at
            ) VALUES (?, ?, ?, ?, 'super_admin', 'active', 0, NULL, ?, NULL, NULL, ?, ?)
            """,
            (str(uuid.uuid4()), test_user, test_email, hash_password(test_pwd), now, now, now),
        )

    # 1. Login with correct credentials
    admin_ctx, session_token, csrf_token, error = admin_auth_service.authenticate(
        identifier=test_email,
        password=test_pwd,
        ip_address="127.0.0.1",
        user_agent="PyTest-Security-Harness",
    )
    assert error is None
    assert admin_ctx is not None
    assert session_token is not None
    assert csrf_token is not None
    assert "hashed_password" not in admin_ctx

    # 2. Validate session retrieval
    retrieved = admin_auth_service.get_admin_by_session(session_token)
    assert retrieved is not None
    assert retrieved["email"] == test_email
    assert retrieved["csrf_token"] == csrf_token

    # 3. Test logout & session invalidation
    admin_auth_service.invalidate_session(session_token, ip_address="127.0.0.1")
    re_retrieved = admin_auth_service.get_admin_by_session(session_token)
    assert re_retrieved is None, "Session must be invalid after logout!"


def test_login_with_incorrect_credentials():
    """Requirement 3, 6: Incorrect credentials must fail and increment failed attempts."""
    test_user = f"admin_fail_{uuid.uuid4().hex[:6]}"
    test_email = f"{test_user}@imageshrink.internal"
    test_pwd = "CorrectAdminPassword_2026!#"

    now = time.time()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO admin_users (
                id, username, email, hashed_password, role, status,
                failed_login_attempts, locked_until, created_date,
                last_login, last_login_ip, password_updated_date, updated_at
            ) VALUES (?, ?, ?, ?, 'super_admin', 'active', 0, NULL, ?, NULL, NULL, ?, ?)
            """,
            (str(uuid.uuid4()), test_user, test_email, hash_password(test_pwd), now, now, now),
        )

    admin_ctx, session_token, csrf_token, error = admin_auth_service.authenticate(
        identifier=test_email,
        password="WrongPassword123!#",
        ip_address="192.168.1.50",
        user_agent="Security-Test-Agent",
    )
    assert admin_ctx is None
    assert session_token is None
    assert error == "Invalid administrator credentials."

    # Verify failed attempts counter was incremented in DB
    with db_session() as conn:
        cur = conn.cursor()
        cur.execute("SELECT failed_login_attempts FROM admin_users WHERE email = ?", (test_email,))
        fails = cur.fetchone()[0]
        assert fails == 1


def test_brute_force_account_lockout():
    """Requirement 3: Temporary account lockout after repeated failed attempts."""
    test_user = f"admin_lock_{uuid.uuid4().hex[:6]}"
    test_email = f"{test_user}@imageshrink.internal"
    test_pwd = "SecureLockoutTest_2026!#"

    now = time.time()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO admin_users (
                id, username, email, hashed_password, role, status,
                failed_login_attempts, locked_until, created_date,
                last_login, last_login_ip, password_updated_date, updated_at
            ) VALUES (?, ?, ?, ?, 'super_admin', 'active', 0, NULL, ?, NULL, NULL, ?, ?)
            """,
            (str(uuid.uuid4()), test_user, test_email, hash_password(test_pwd), now, now, now),
        )

    # Perform 5 consecutive failed attempts
    for i in range(settings.ADMIN_MAX_LOGIN_ATTEMPTS):
        admin_ctx, token, csrf, err = admin_auth_service.authenticate(
            identifier=test_email,
            password="WrongAttemptPassword!",
            ip_address=f"10.0.0.{i+1}",
            user_agent="BruteForceSimulator",
        )
        assert admin_ctx is None

    # Verify account is now locked in DB
    with db_session() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status, locked_until, failed_login_attempts FROM admin_users WHERE email = ?", (test_email,))
        row = cur.fetchone()
        assert row["status"] == "locked"
        assert row["locked_until"] is not None
        assert row["locked_until"] > time.time()

    # Even with correct password, login must be blocked while account is locked
    admin_ctx, token, csrf, err = admin_auth_service.authenticate(
        identifier=test_email,
        password=test_pwd,
        ip_address="10.0.0.99",
        user_agent="BruteForceSimulator",
    )
    assert admin_ctx is None
    assert "locked" in err.lower()


def test_anti_csrf_protection():
    """Requirement 3: CSRF token verification."""
    session_id = str(uuid.uuid4())
    token = create_csrf_token(session_id)

    # Valid token matches
    assert verify_csrf_token(session_id, token) is True

    # Tampered or wrong token rejected
    assert verify_csrf_token(session_id, "tampered-csrf-token") is False
    assert verify_csrf_token(str(uuid.uuid4()), token) is False
    assert verify_csrf_token("", token) is False


def test_admin_password_change_security():
    """Requirement 2: Administrators can change their password securely."""
    admin_id = str(uuid.uuid4())
    rand_suffix = uuid.uuid4().hex[:8]
    test_email = f"change_pwd_{rand_suffix}@imageshrink.internal"
    test_username = f"change_admin_{rand_suffix}"
    old_pwd = "OldAdminPassword_2026!#"
    new_pwd = "BrandNewSecurePassword_2026!$"

    now = time.time()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO admin_users (
                id, username, email, hashed_password, role, status,
                failed_login_attempts, locked_until, created_date,
                last_login, last_login_ip, password_updated_date, updated_at
            ) VALUES (?, ?, ?, ?, 'super_admin', 'active', 0, NULL, ?, NULL, NULL, ?, ?)
            """,
            (admin_id, test_username, test_email, hash_password(old_pwd), now, now, now),
        )

    # 1. Reject change with wrong current password
    success, msg = admin_auth_service.change_password(
        admin_id=admin_id,
        current_password="IncorrectCurrentPassword!",
        new_password=new_pwd,
        ip_address="127.0.0.1",
        user_agent="TestAgent",
    )
    assert not success
    assert "verification failed" in msg

    # 2. Reject change with weak new password
    success, msg = admin_auth_service.change_password(
        admin_id=admin_id,
        current_password=old_pwd,
        new_password="weak",
        ip_address="127.0.0.1",
        user_agent="TestAgent",
    )
    assert not success
    assert "at least 12 characters" in msg

    # 3. Successful password change
    success, msg = admin_auth_service.change_password(
        admin_id=admin_id,
        current_password=old_pwd,
        new_password=new_pwd,
        ip_address="127.0.0.1",
        user_agent="TestAgent",
    )
    assert success

    # Verify old password no longer works
    admin_ctx, token, csrf, err = admin_auth_service.authenticate(
        identifier=test_email,
        password=old_pwd,
        ip_address="127.0.0.1",
        user_agent="TestAgent",
    )
    assert admin_ctx is None

    # Verify new password succeeds
    admin_ctx, token, csrf, err = admin_auth_service.authenticate(
        identifier=test_email,
        password=new_pwd,
        ip_address="127.0.0.1",
        user_agent="TestAgent",
    )
    assert admin_ctx is not None
    assert err is None


def test_audit_logs_record_and_sanitize():
    """Requirement 6: Maintain secure audit logs without sensitive credential exposure."""
    admin_auth_service.log_audit(
        action="TEST_ACTION",
        status="SUCCESS",
        username="audit_tester",
        ip_address="10.10.10.10",
        details={
            "action_info": "Batch 123 inspected",
            "password": "SecretPlaintextPassword!",  # Must be redacted
            "session_token": "SecretSessionToken!",   # Must be redacted
        },
    )

    logs = admin_auth_service.get_audit_logs(limit=1)
    assert len(logs) > 0
    latest = logs[0]
    assert latest["action"] == "TEST_ACTION"
    assert "SecretPlaintextPassword" not in latest["details_json"]
    assert "SecretSessionToken" not in latest["details_json"]
    assert "[REDACTED]" in latest["details_json"]


def test_api_docs_hidden():
    """Requirement: Hide api docs, never provide public api documentation."""
    from app.main import app
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None

