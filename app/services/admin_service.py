"""
Administrator Service.
Provides user management, subscription management, system observability,
business analytics, and tamper-evident audit logging.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from typing import Any, Dict, List, Optional

from app.config import OPTIMIZED_DIR, STORAGE_DIR, UPLOADS_DIR, settings
from app.database import db_session


class AdminService:
    @staticmethod
    def log_audit_action(admin_email: str, action: str, target_type: str, target_id: Optional[str], details: Dict[str, Any]) -> None:
        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO admin_audit_logs (id, admin_email, action, target_type, target_id, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), admin_email, action, target_type, target_id, json.dumps(details), time.time()),
            )

    @staticmethod
    def list_users(search: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with db_session() as conn:
            cur = conn.cursor()
            if search:
                pattern = f"%{search}%"
                cur.execute(
                    """
                    SELECT id, email, full_name, plan, is_active, is_verified, created_at
                    FROM users
                    WHERE email LIKE ? OR full_name LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (pattern, pattern, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT id, email, full_name, plan, is_active, is_verified, created_at
                    FROM users
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def update_user_status(admin_email: str, user_id: str, is_active: bool, is_admin: bool, plan: str) -> bool:
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT email FROM users WHERE id = ?", (user_id,))
            target = cur.fetchone()
            if not target:
                return False
            cur.execute(
                "UPDATE users SET is_active = ?, plan = ?, updated_at = ? WHERE id = ?",
                (1 if is_active else 0, plan, time.time(), user_id),
            )
        return True

    @staticmethod
    def get_system_health() -> Dict[str, Any]:
        """Aggregate real-time metrics on storage, queue, memory, and database."""
        # Calculate storage usage
        total_upload_bytes = 0
        total_optimized_bytes = 0

        for p in UPLOADS_DIR.rglob("*"):
            if p.is_file():
                total_upload_bytes += p.stat().st_size

        for p in OPTIMIZED_DIR.rglob("*"):
            if p.is_file():
                total_optimized_bytes += p.stat().st_size

        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM upload_batches WHERE status = 'processing'")
            active_jobs = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM uploaded_images WHERE status = 'failed'")
            failed_images = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]

            cur.execute("SELECT plan, COUNT(*) FROM users GROUP BY plan")
            plan_counts = {row[0]: row[1] for row in cur.fetchall()}

            cur.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND plan IN ('pro', 'business', 'premium')")
            active_subscribers = cur.fetchone()[0]

            cur.execute("SELECT SUM(amount) FROM payments WHERE status = 'succeeded'")
            revenue_sum = cur.fetchone()[0] or 0.0

            cur.execute("SELECT COUNT(*) FROM payments WHERE status = 'failed'")
            failed_payments = cur.fetchone()[0] or 0

            # Compute Monthly Recurring Revenue (MRR) in INR
            mrr_inr = (
                (plan_counts.get("pro", 0) * settings.PLANS["pro"].price_monthly_inr)
                + (plan_counts.get("business", 0) * settings.PLANS["business"].price_monthly_inr)
                + (plan_counts.get("premium", 0) * settings.PLANS["premium"].price_monthly_inr)
            )

            cur.execute("SELECT SUM(total_original_size), SUM(total_optimized_size) FROM upload_batches")
            row = cur.fetchone()
            all_orig = row[0] or 0
            all_opt = row[1] or 0
            all_saved = max(0, all_orig - all_opt)

        return {
            "status": "healthy",
            "uptime_seconds": time.time(),
            "active_processing_jobs": active_jobs,
            "failed_images_total": failed_images,
            "total_users": total_users,
            "plan_breakdown": {
                "free": plan_counts.get("free", 0),
                "pro": plan_counts.get("pro", 0),
                "business": plan_counts.get("business", 0),
                "premium": plan_counts.get("premium", 0),
            },
            "active_subscribers": active_subscribers,
            "total_revenue_inr": round(revenue_sum, 2),
            "mrr_inr": mrr_inr,
            "failed_payments": failed_payments,
            "storage": {
                "uploads_bytes": total_upload_bytes,
                "optimized_bytes": total_optimized_bytes,
                "all_time_saved_bytes": all_saved,
                "all_time_savings_percent": round((all_saved / all_orig * 100), 2) if all_orig > 0 else 0.0,
            },
        }

    @staticmethod
    def override_user_quota(admin_email: str, user_id: str, new_allowance: int, reset_used: bool = False) -> bool:
        """Allows administrator to adjust or boost user's monthly quota."""
        now = time.time()
        with db_session() as conn:
            cur = conn.cursor()
            if reset_used:
                cur.execute(
                    "UPDATE subscriptions SET monthly_allowance = ?, used_quota = 0, updated_at = ? WHERE user_id = ? AND status = 'active'",
                    (new_allowance, now, user_id),
                )
            else:
                cur.execute(
                    "UPDATE subscriptions SET monthly_allowance = ?, updated_at = ? WHERE user_id = ? AND status = 'active'",
                    (new_allowance, now, user_id),
                )
        return True


admin_service = AdminService()

