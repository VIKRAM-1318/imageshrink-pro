"""
ImageShrink Pro V2 Database Architecture.
High-performance SQLite engine with schema definitions, admin access control structures,
and query helpers.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import BASE_DIR, STORAGE_DIR, settings

logger = logging.getLogger("imageshrink.database")
DB_FILE = BASE_DIR / "imageshrink_v2.db"


def get_db_connection() -> sqlite3.Connection:
    """Create a connection configured with WAL journal mode, busy timeouts, and dict row factory."""
    conn = sqlite3.connect(str(DB_FILE), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def db_session():
    """Context manager for atomic database transactions."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize all schema tables and indexes."""
    with db_session() as conn:
        conn.executescript("""
        -- =======================================================
        -- 1. PUBLIC APP USERS & SESSIONS
        -- =======================================================
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            plan TEXT NOT NULL DEFAULT 'free',
            is_active INTEGER NOT NULL DEFAULT 1,
            is_verified INTEGER NOT NULL DEFAULT 0,
            email_verified_at REAL,
            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until REAL,
            google_id TEXT,
            last_login REAL,
            last_login_ip TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            expires_at REAL NOT NULL,
            is_remembered INTEGER NOT NULL DEFAULT 0,
            last_active REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS email_verification_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            email TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            expires_at REAL NOT NULL,
            used_at REAL,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at REAL NOT NULL,
            used_at REAL,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS login_activity (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            email TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            status TEXT NOT NULL,
            failure_reason TEXT,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_security_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            details_json TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS email_delivery_logs (
            id TEXT PRIMARY KEY,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            template_name TEXT NOT NULL,
            idempotency_key TEXT,
            message_id TEXT,
            status TEXT NOT NULL,
            error_details TEXT,
            attempts INTEGER NOT NULL DEFAULT 1,
            sent_at REAL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS google_oauth_credentials (
            id TEXT PRIMARY KEY,
            service_type TEXT NOT NULL,
            client_id TEXT,
            client_secret_enc TEXT,
            refresh_token_enc TEXT,
            access_token_enc TEXT,
            token_expiry REAL,
            sender_email TEXT,
            sender_name TEXT,
            updated_at REAL NOT NULL
        );

        -- =======================================================
        -- 2. DEDICATED PRIVATE ADMIN USERS & SESSIONS
        -- =======================================================
        CREATE TABLE IF NOT EXISTS admin_users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'super_admin',
            status TEXT NOT NULL DEFAULT 'active',
            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until REAL,
            created_date REAL NOT NULL,
            last_login REAL,
            last_login_ip TEXT,
            password_updated_date REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admin_sessions (
            id TEXT PRIMARY KEY,
            admin_id TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            csrf_token TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            expires_at REAL NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (admin_id) REFERENCES admin_users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS admin_audit_logs (
            id TEXT PRIMARY KEY,
            admin_id TEXT,
            admin_username TEXT,
            admin_email TEXT,
            action TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            status TEXT NOT NULL,
            details_json TEXT,
            created_at REAL NOT NULL
        );

        -- =======================================================
        -- 3. SUBSCRIPTIONS, BATCHES & PROCESSING RESULTS
        -- =======================================================
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active',
            billing_cycle TEXT NOT NULL DEFAULT 'monthly',
            monthly_allowance INTEGER NOT NULL DEFAULT 50,
            used_quota INTEGER NOT NULL DEFAULT 0,
            current_period_start REAL NOT NULL DEFAULT 0,
            current_period_end REAL NOT NULL DEFAULT 0,
            cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
            provider TEXT DEFAULT 'system',
            provider_subscription_id TEXT,
            provider_payment_id TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            subscription_id TEXT,
            invoice_number TEXT UNIQUE NOT NULL,
            plan TEXT NOT NULL,
            billing_cycle TEXT NOT NULL DEFAULT 'monthly',
            amount_inr REAL NOT NULL,
            tax_inr REAL NOT NULL DEFAULT 0,
            total_inr REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'paid',
            payment_method TEXT DEFAULT 'UPI / Card',
            provider TEXT NOT NULL DEFAULT 'razorpay',
            provider_payment_id TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS processing_audit_history (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            batch_id TEXT NOT NULL,
            image_id TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            input_format TEXT NOT NULL,
            output_format TEXT NOT NULL,
            original_size INTEGER NOT NULL,
            optimized_size INTEGER NOT NULL,
            status TEXT NOT NULL,
            quota_deducted INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            status TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_payment_id TEXT,
            invoice_number TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS upload_batches (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            name TEXT NOT NULL,
            total_files INTEGER NOT NULL DEFAULT 0,
            processed_files INTEGER NOT NULL DEFAULT 0,
            failed_files INTEGER NOT NULL DEFAULT 0,
            total_original_size INTEGER NOT NULL DEFAULT 0,
            total_optimized_size INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            mode TEXT NOT NULL DEFAULT 'lossless',
            settings_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            completed_at REAL
        );

        CREATE TABLE IF NOT EXISTS uploaded_images (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            original_format TEXT NOT NULL,
            original_size INTEGER NOT NULL,
            original_width INTEGER,
            original_height INTEGER,
            storage_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (batch_id) REFERENCES upload_batches(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS optimization_results (
            id TEXT PRIMARY KEY,
            image_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            output_filename TEXT NOT NULL,
            output_format TEXT NOT NULL,
            output_size INTEGER NOT NULL,
            output_width INTEGER,
            output_height INTEGER,
            bytes_saved INTEGER NOT NULL DEFAULT 0,
            percentage_saved REAL NOT NULL DEFAULT 0.0,
            ssim_score REAL,
            psnr_score REAL,
            storage_path TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (image_id) REFERENCES uploaded_images(id) ON DELETE CASCADE,
            FOREIGN KEY (batch_id) REFERENCES upload_batches(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            prefix TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_used_at REAL,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS promo_codes (
            id TEXT PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            discount_percent REAL NOT NULL,
            max_uses INTEGER NOT NULL DEFAULT 100,
            current_uses INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            expires_at REAL
        );

        -- Performance Indexes
        CREATE INDEX IF NOT EXISTS idx_batches_user_id ON upload_batches(user_id);
        CREATE INDEX IF NOT EXISTS idx_uploaded_images_batch ON uploaded_images(batch_id);
        CREATE INDEX IF NOT EXISTS idx_results_batch ON optimization_results(batch_id);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email);
        CREATE INDEX IF NOT EXISTS idx_admin_users_username ON admin_users(username);
        CREATE INDEX IF NOT EXISTS idx_invoices_user ON invoices(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_history_user ON processing_audit_history(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_history_created ON processing_audit_history(created_at);
        CREATE INDEX IF NOT EXISTS idx_email_verify_token ON email_verification_tokens(token_hash);
        CREATE INDEX IF NOT EXISTS idx_pwd_reset_token ON password_reset_tokens(token_hash);
        CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_login_activity_email ON login_activity(email);
        CREATE INDEX IF NOT EXISTS idx_delivery_logs_recipient ON email_delivery_logs(recipient);
        CREATE INDEX IF NOT EXISTS idx_delivery_logs_idempotency ON email_delivery_logs(idempotency_key);
        """)

        # Execute safe column migrations for existing SQLite databases
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(subscriptions);")
        sub_cols = {row["name"] for row in cur.fetchall()}
        
        migration_cols = [
            ("billing_cycle", "TEXT NOT NULL DEFAULT 'monthly'"),
            ("monthly_allowance", "INTEGER NOT NULL DEFAULT 50"),
            ("used_quota", "INTEGER NOT NULL DEFAULT 0"),
            ("current_period_start", "REAL NOT NULL DEFAULT 0"),
            ("provider_payment_id", "TEXT"),
            ("updated_at", "REAL NOT NULL DEFAULT 0"),
        ]
        for col_name, col_def in migration_cols:
            if col_name not in sub_cols:
                try:
                    cur.execute(f"ALTER TABLE subscriptions ADD COLUMN {col_name} {col_def};")
                except Exception as e:
                    logger.debug(f"Column migration skipped for {col_name}: {e}")

        # Safe column migrations for users table
        cur.execute("PRAGMA table_info(users);")
        user_cols = {row["name"] for row in cur.fetchall()}
        user_migrations = [
            ("email_verified_at", "REAL"),
            ("failed_login_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ("locked_until", "REAL"),
            ("google_id", "TEXT"),
            ("last_login", "REAL"),
            ("last_login_ip", "TEXT"),
        ]
        for col_name, col_def in user_migrations:
            if col_name not in user_cols:
                try:
                    cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def};")
                except Exception as e:
                    logger.debug(f"Column migration skipped for users.{col_name}: {e}")

        # Safe column migrations for user_sessions table
        cur.execute("PRAGMA table_info(user_sessions);")
        sess_cols = {row["name"] for row in cur.fetchall()}
        sess_migrations = [
            ("is_remembered", "INTEGER NOT NULL DEFAULT 0"),
            ("last_active", "REAL NOT NULL DEFAULT 0"),
        ]
        for col_name, col_def in sess_migrations:
            if col_name not in sess_cols:
                try:
                    cur.execute(f"ALTER TABLE user_sessions ADD COLUMN {col_name} {col_def};")
                except Exception as e:
                    logger.debug(f"Column migration skipped for user_sessions.{col_name}: {e}")

    # Secure Initial Admin Provisioning
    seed_default_data()


def seed_default_data() -> None:
    """Provisions initial administrator account securely using environment variables without hardcoded credentials."""
    from app.security import hash_password

    with db_session() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM admin_users LIMIT 1")
        existing_admin = cur.fetchone()

        now = time.time()
        if not existing_admin:
            # Check environment variables
            admin_email = settings.INITIAL_ADMIN_EMAIL
            admin_username = admin_email.split("@")[0] or "admin"

            # If password is provided via environment, use it; otherwise generate a cryptographically secure one-time secret
            if settings.INITIAL_ADMIN_PASSWORD:
                admin_password = settings.INITIAL_ADMIN_PASSWORD
            else:
                admin_password = f"Admin!{secrets.token_urlsafe(12)}"
                # Persist secure one-time notice in storage/
                notice_file = STORAGE_DIR / "initial_admin_credentials_notice.txt"
                notice_content = (
                    "====================================================================\n"
                    "IMAGE SHRINK PRO V2 - SECURE INITIAL ADMINISTRATOR PROVISIONING\n"
                    "====================================================================\n"
                    "Initial administrator account has been auto-generated because no\n"
                    "INITIAL_ADMIN_PASSWORD was supplied in environment variables.\n\n"
                    f"Admin Portal URL : {settings.ADMIN_PATH_PREFIX}/login\n"
                    f"Username / Email : {admin_email}\n"
                    f"Temporary Pass   : {admin_password}\n\n"
                    "SECURITY NOTICE: Log in immediately at the admin portal and change\n"
                    "this password. Delete this file after initial access.\n"
                    "====================================================================\n"
                )
                try:
                    notice_file.write_text(notice_content, encoding="utf-8")
                    logger.warning("Secure initial admin credentials written to storage/initial_admin_credentials_notice.txt")
                except Exception:
                    pass

            admin_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO admin_users (
                    id, username, email, hashed_password, role, status,
                    failed_login_attempts, locked_until, created_date,
                    last_login, last_login_ip, password_updated_date, updated_at
                ) VALUES (?, ?, ?, ?, 'super_admin', 'active', 0, NULL, ?, NULL, NULL, ?, ?)
                """,
                (
                    admin_id,
                    admin_username,
                    admin_email,
                    hash_password(admin_password),
                    now,
                    now,
                    now,
                ),
            )

        # Seed sample promo codes if not present
        cur.execute("SELECT id FROM promo_codes WHERE code = 'LAUNCH50'")
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO promo_codes (id, code, discount_percent, max_uses, current_uses, is_active, expires_at)
                VALUES (?, 'LAUNCH50', 50.0, 500, 0, 1, ?)
                """,
                (str(uuid.uuid4()), now + 180 * 86400),
            )
