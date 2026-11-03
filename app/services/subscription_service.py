"""
ImageShrink Pro V2 Subscription & Quota Management Service.
Centralized, scalable, and atomic tracking of:
- Subscription plans (Free, Pro, Business, Premium)
- Format-based access controls
- Monthly quotas and atomic deductions
- Billing cycle auto-renewals & resets
- Invoices & processing audit history
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.config import (
    get_plan_hierarchy,
    get_required_plan_for_format,
    is_format_allowed_for_plan,
    settings,
)
from app.database import db_session

logger = logging.getLogger("imageshrink.subscriptions")


class SubscriptionService:
    @staticmethod
    def get_user_subscription(user_id: Optional[str]) -> Dict[str, Any]:
        """
        Retrieves active subscription for user with automatic billing cycle checking.
        Unauthenticated / Guest users receive default Free plan limits.
        """
        now = time.time()
        if not user_id:
            free_limits = settings.PLANS["free"]
            return {
                "user_id": None,
                "plan": "free",
                "plan_name": "Free",
                "status": "active",
                "billing_cycle": "forever",
                "monthly_allowance": free_limits.monthly_allowance,
                "used_quota": 0,
                "remaining_quota": free_limits.monthly_allowance,
                "usage_percentage": 0.0,
                "max_batch_size": free_limits.max_batch_size,
                "max_file_size_mb": free_limits.max_file_size_mb,
                "allowed_formats": free_limits.allowed_formats,
                "allowed_modes": free_limits.allowed_modes,
                "priority_level": free_limits.priority_level,
                "ad_free": free_limits.ad_free,
                "allow_api_access": free_limits.allow_api_access,
                "allow_bulk_conversion": free_limits.allow_bulk_conversion,
                "current_period_start": now,
                "current_period_end": now + 30 * 86400,
                "cancel_at_period_end": False,
                "provider": "system",
            }

        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 
                    id, user_id, plan, status, billing_cycle, monthly_allowance,
                    used_quota, current_period_start, current_period_end,
                    cancel_at_period_end, provider, provider_subscription_id,
                    provider_payment_id, created_at, updated_at
                FROM subscriptions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()

            if not row:
                # Initialize new Free subscription record
                sub_id = str(uuid.uuid4())
                free_limits = settings.PLANS["free"]
                period_start = now
                period_end = now + 30 * 86400

                cur.execute(
                    """
                    INSERT INTO subscriptions (
                        id, user_id, plan, status, billing_cycle, monthly_allowance,
                        used_quota, current_period_start, current_period_end,
                        cancel_at_period_end, provider, created_at, updated_at
                    ) VALUES (?, ?, 'free', 'active', 'monthly', ?, 0, ?, ?, 0, 'system', ?, ?)
                    """,
                    (sub_id, user_id, free_limits.monthly_allowance, period_start, period_end, now, now),
                )
                cur.execute("UPDATE users SET plan = 'free' WHERE id = ?", (user_id,))
                
                return {
                    "subscription_id": sub_id,
                    "user_id": user_id,
                    "plan": "free",
                    "plan_name": "Free",
                    "status": "active",
                    "billing_cycle": "monthly",
                    "monthly_allowance": free_limits.monthly_allowance,
                    "used_quota": 0,
                    "remaining_quota": free_limits.monthly_allowance,
                    "usage_percentage": 0.0,
                    "max_batch_size": free_limits.max_batch_size,
                    "max_file_size_mb": free_limits.max_file_size_mb,
                    "allowed_formats": free_limits.allowed_formats,
                    "allowed_modes": free_limits.allowed_modes,
                    "priority_level": free_limits.priority_level,
                    "ad_free": free_limits.ad_free,
                    "allow_api_access": free_limits.allow_api_access,
                    "allow_bulk_conversion": free_limits.allow_bulk_conversion,
                    "current_period_start": period_start,
                    "current_period_end": period_end,
                    "cancel_at_period_end": False,
                    "provider": "system",
                }

            sub_dict = dict(row)
            plan_name = sub_dict.get("plan", "free").lower()
            plan_limits = settings.PLANS.get(plan_name, settings.PLANS["free"])
            allowance = sub_dict.get("monthly_allowance") or plan_limits.monthly_allowance

            # Check if current billing cycle has expired -> Atomic Quota Reset
            period_end = sub_dict.get("current_period_end", 0)
            used_quota = sub_dict.get("used_quota", 0)

            if now >= period_end and period_end > 0:
                cycle_duration = 365 * 86400 if sub_dict.get("billing_cycle") == "annual" else 30 * 86400
                new_start = now
                new_end = now + cycle_duration
                used_quota = 0

                # Check if subscription was marked to cancel at period end
                new_status = "expired" if sub_dict.get("cancel_at_period_end") else sub_dict.get("status", "active")
                if new_status == "expired":
                    plan_name = "free"
                    allowance = settings.PLANS["free"].monthly_allowance
                    cur.execute("UPDATE users SET plan = 'free' WHERE id = ?", (user_id,))

                cur.execute(
                    """
                    UPDATE subscriptions
                    SET used_quota = 0, current_period_start = ?, current_period_end = ?, status = ?, plan = ?, monthly_allowance = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (new_start, new_end, new_status, plan_name, allowance, now, sub_dict["id"]),
                )
                sub_dict["current_period_start"] = new_start
                sub_dict["current_period_end"] = new_end
                sub_dict["status"] = new_status
                sub_dict["plan"] = plan_name
                sub_dict["monthly_allowance"] = allowance

            plan_limits = settings.PLANS.get(plan_name, settings.PLANS["free"])
            remaining = max(0, allowance - used_quota)
            pct = round((used_quota / allowance * 100.0), 1) if allowance > 0 else 0.0

            return {
                "subscription_id": sub_dict.get("id"),
                "user_id": user_id,
                "plan": plan_name,
                "plan_name": plan_limits.name,
                "status": sub_dict.get("status", "active"),
                "billing_cycle": sub_dict.get("billing_cycle", "monthly"),
                "monthly_allowance": allowance,
                "used_quota": used_quota,
                "remaining_quota": remaining,
                "usage_percentage": min(100.0, pct),
                "max_batch_size": plan_limits.max_batch_size,
                "max_file_size_mb": plan_limits.max_file_size_mb,
                "allowed_formats": plan_limits.allowed_formats,
                "allowed_modes": plan_limits.allowed_modes,
                "priority_level": plan_limits.priority_level,
                "ad_free": plan_limits.ad_free,
                "allow_api_access": plan_limits.allow_api_access,
                "allow_bulk_conversion": plan_limits.allow_bulk_conversion,
                "allow_custom_dimensions": plan_limits.allow_custom_dimensions,
                "allow_target_file_size": plan_limits.allow_target_file_size,
                "allow_saved_presets": plan_limits.allow_saved_presets,
                "allow_reports": plan_limits.allow_reports,
                "current_period_start": sub_dict.get("current_period_start"),
                "current_period_end": sub_dict.get("current_period_end"),
                "cancel_at_period_end": bool(sub_dict.get("cancel_at_period_end")),
                "provider": sub_dict.get("provider", "system"),
            }

    @classmethod
    def verify_processing_permission(
        cls,
        user_id: Optional[str],
        file_count: int,
        file_sizes: List[int],
        input_formats: List[str],
        target_format: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates batch processing request against user's active subscription:
        1. Batch size limit check
        2. Individual file size limit check
        3. Input formats permission check (Table 2)
        4. Target output format conversion check (Table 2)
        5. Available monthly quota check
        """
        sub = cls.get_user_subscription(user_id)
        plan_name = sub["plan"]
        max_batch = sub["max_batch_size"]
        max_mb = sub["max_file_size_mb"]
        max_bytes = max_mb * 1024 * 1024
        remaining_quota = sub["remaining_quota"]

        # 1. Batch size limit
        if file_count > max_batch:
            return (
                False,
                f"Batch size ({file_count} images) exceeds your {sub['plan_name']} plan limit of {max_batch} images per batch. Upgrade your subscription to process larger batches.",
                {"code": "BATCH_SIZE_EXCEEDED", "limit": max_batch, "requested": file_count},
            )

        # 2. Individual file size limit
        for idx, size in enumerate(file_sizes):
            if size > max_bytes:
                return (
                    False,
                    f"File #{idx + 1} ({size / (1024 * 1024):.1f} MB) exceeds your {sub['plan_name']} plan maximum file limit of {max_mb} MB.",
                    {"code": "FILE_SIZE_EXCEEDED", "limit_mb": max_mb, "file_index": idx},
                )

        # 3. Input formats verification
        for fmt in input_formats:
            clean_fmt = fmt.lower().lstrip(".")
            if not is_format_allowed_for_plan(clean_fmt, plan_name):
                req_plan = get_required_plan_for_format(clean_fmt)
                return (
                    False,
                    f"Format '{clean_fmt.upper()}' is not supported on the {sub['plan_name']} plan. Upgrade to the {req_plan} plan to process {clean_fmt.upper()} files.",
                    {"code": "FORMAT_RESTRICTED", "format": clean_fmt, "required_plan": req_plan},
                )

        # 4. Target format conversion verification
        if target_format and target_format.lower() not in ("original", "", "none"):
            clean_tgt = target_format.lower().lstrip(".")
            if not is_format_allowed_for_plan(clean_tgt, plan_name):
                req_plan = get_required_plan_for_format(clean_tgt)
                return (
                    False,
                    f"Converting images to '{clean_tgt.upper()}' requires the {req_plan} plan. Please upgrade your subscription.",
                    {"code": "TARGET_FORMAT_RESTRICTED", "target_format": clean_tgt, "required_plan": req_plan},
                )

        # 5. Monthly quota verification
        if remaining_quota < file_count:
            return (
                False,
                f"Insufficient monthly quota. You have {remaining_quota} image operations remaining, but requested {file_count}. Please upgrade your subscription for additional quota.",
                {"code": "QUOTA_EXHAUSTED", "remaining_quota": remaining_quota, "requested": file_count},
            )

        return True, "Authorized", sub

    @staticmethod
    def deduct_quota_atomic(
        user_id: Optional[str],
        successful_count: int,
        batch_id: str,
        results: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Deducts quota strictly and atomically for successfully processed images only.
        Failed images NEVER consume quota.
        Records an auditable processing history log.
        """
        if not user_id or successful_count <= 0:
            return True

        now = time.time()
        with db_session() as conn:
            cur = conn.cursor()
            # Atomic update preventing negative quota or concurrent race conditions
            cur.execute(
                """
                UPDATE subscriptions
                SET used_quota = used_quota + ?, updated_at = ?
                WHERE user_id = ? AND status = 'active'
                """,
                (successful_count, now, user_id),
            )

            # Record audit history for individual processed results
            if results:
                for r in results:
                    is_success = r.get("processing_status") == "Completed" or r.get("status") == "Completed"
                    quota_used = 1 if is_success else 0
                    cur.execute(
                        """
                        INSERT INTO processing_audit_history (
                            id, user_id, batch_id, image_id, original_filename,
                            input_format, output_format, original_size,
                            optimized_size, status, quota_deducted, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            user_id,
                            batch_id,
                            r.get("id") or r.get("image_id") or str(uuid.uuid4()),
                            r.get("name") or r.get("original_filename") or "image",
                            r.get("original_format") or "unknown",
                            r.get("output_format") or r.get("format") or "unknown",
                            r.get("before") or r.get("original_size") or 0,
                            r.get("after") or r.get("optimized_size") or 0,
                            "Completed" if is_success else "Failed",
                            quota_used,
                            now,
                        ),
                    )

            logger.info(f"Deducted {successful_count} quota units for user {user_id} (batch {batch_id}).")
            return True

    @staticmethod
    def activate_subscription(
        user_id: str,
        plan_name: str,
        billing_cycle: str = "monthly",
        provider: str = "razorpay",
        provider_payment_id: Optional[str] = None,
        provider_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Activates or upgrades a user's subscription, creates an official invoice with 18% GST,
        and logs the transaction.
        """
        plan_name = plan_name.lower()
        if plan_name not in settings.PLANS:
            raise ValueError(f"Unknown subscription plan: {plan_name}")

        plan_limits = settings.PLANS[plan_name]
        is_annual = billing_cycle.lower() == "annual"
        amount = plan_limits.price_annual_inr if is_annual else plan_limits.price_monthly_inr

        # Calculate GST (18%)
        base_amount = round(amount / 1.18, 2)
        tax_gst = round(amount - base_amount, 2)

        now = time.time()
        cycle_duration = 365 * 86400 if is_annual else 30 * 86400
        period_start = now
        period_end = now + cycle_duration

        sub_id = str(uuid.uuid4())
        inv_number = f"INV-ISP-{int(now)}-{uuid.uuid4().hex[:4].upper()}"

        with db_session() as conn:
            cur = conn.cursor()
            # Update user profile
            cur.execute("UPDATE users SET plan = ?, updated_at = ? WHERE id = ?", (plan_name, now, user_id))

            # Mark any previous active subscriptions as superseded
            cur.execute(
                "UPDATE subscriptions SET status = 'superseded', updated_at = ? WHERE user_id = ? AND status = 'active'",
                (now, user_id),
            )

            # Insert new active subscription with full monthly allowance
            cur.execute(
                """
                INSERT INTO subscriptions (
                    id, user_id, plan, status, billing_cycle, monthly_allowance,
                    used_quota, current_period_start, current_period_end,
                    cancel_at_period_end, provider, provider_subscription_id,
                    provider_payment_id, created_at, updated_at
                ) VALUES (?, ?, ?, 'active', ?, ?, 0, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    sub_id,
                    user_id,
                    plan_name,
                    billing_cycle,
                    plan_limits.monthly_allowance,
                    period_start,
                    period_end,
                    provider,
                    provider_order_id,
                    provider_payment_id,
                    now,
                    now,
                ),
            )

            # Generate formal invoice
            if amount > 0:
                cur.execute(
                    """
                    INSERT INTO invoices (
                        id, user_id, subscription_id, invoice_number, plan,
                        billing_cycle, amount_inr, tax_inr, total_inr, status,
                        payment_method, provider, provider_payment_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'paid', 'UPI / Card / NetBanking', ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        sub_id,
                        inv_number,
                        plan_limits.name,
                        billing_cycle,
                        base_amount,
                        tax_gst,
                        amount,
                        provider,
                        provider_payment_id,
                        now,
                    ),
                )
                # Payment record
                cur.execute(
                    """
                    INSERT INTO payments (
                        id, user_id, amount, currency, status, provider,
                        provider_payment_id, invoice_number, created_at
                    ) VALUES (?, ?, ?, 'INR', 'succeeded', ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), user_id, amount, provider, provider_payment_id, inv_number, now),
                )

        logger.info(f"User {user_id} activated {plan_name.upper()} plan ({billing_cycle}) for ₹{amount}.")
        return {
            "success": True,
            "subscription_id": sub_id,
            "plan": plan_name,
            "plan_name": plan_limits.name,
            "monthly_allowance": plan_limits.monthly_allowance,
            "billing_cycle": billing_cycle,
            "amount_paid_inr": amount,
            "invoice_number": inv_number if amount > 0 else None,
            "period_end": period_end,
        }

    @staticmethod
    def cancel_subscription(user_id: str) -> Dict[str, Any]:
        """Sets subscription to cancel at current period end without revoking remaining days."""
        now = time.time()
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE subscriptions
                SET cancel_at_period_end = 1, updated_at = ?
                WHERE user_id = ? AND status = 'active'
                """,
                (now, user_id),
            )
        return {"success": True, "message": "Subscription will not renew after the current billing cycle."}

    @staticmethod
    def get_invoices(user_id: str) -> List[Dict[str, Any]]:
        """Returns billing invoices for the user."""
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, invoice_number, plan, billing_cycle, amount_inr, tax_inr, total_inr, status, payment_method, created_at
                FROM invoices
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def get_processing_history(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent auditable processing history for the user dashboard."""
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, batch_id, original_filename, input_format, output_format,
                       original_size, optimized_size, status, quota_deducted, created_at
                FROM processing_audit_history
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]


subscription_service = SubscriptionService()

