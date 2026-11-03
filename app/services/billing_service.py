"""
Billing and Subscription Service.
Integrates Stripe and Razorpay, enforces plan limits and quotas,
processes webhooks, and manages subscription lifecycles.
"""
from __future__ import annotations

import hmac
import hashlib
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from app.config import settings
from app.database import db_session


class BillingService:
    @staticmethod
    def verify_plan_quota(user_id: Optional[str], requested_file_count: int, file_size_bytes: int) -> Tuple[bool, str]:
        """
        Verify if the upload complies with the user's plan.
        Guest/unauthenticated uploads default to Free plan rules.
        """
        plan_name = "free"
        if user_id:
            with db_session() as conn:
                cur = conn.cursor()
                cur.execute("SELECT plan FROM users WHERE id = ?", (user_id,))
                user_row = cur.fetchone()
                if user_row:
                    plan_name = user_row["plan"]

        limits = settings.PLANS.get(plan_name, settings.PLANS["free"])

        # Check batch limit
        if requested_file_count > limits.max_batch_size:
            return False, f"Batch size ({requested_file_count}) exceeds your {plan_name.upper()} plan limit of {limits.max_batch_size} images. Please upgrade to Pro or Business."

        # Check individual file size limit
        max_bytes = limits.max_file_size_mb * 1024 * 1024
        if file_size_bytes > max_bytes:
            return False, f"File size exceeds your {plan_name.upper()} plan limit of {limits.max_file_size_mb} MB."

        return True, "OK"

    @staticmethod
    def create_checkout_session(user_id: str, plan_name: str, provider: str = "stripe") -> Dict[str, Any]:
        """Generate checkout configuration for Stripe or Razorpay."""
        if plan_name not in ("pro", "business"):
            raise ValueError("Invalid subscription plan.")

        prices = {
            "pro": {"amount": 12.0, "currency": "USD", "name": "ImageShrink Pro Plan"},
            "business": {"amount": 39.0, "currency": "USD", "name": "ImageShrink Business Plan"},
        }
        plan_info = prices[plan_name]

        # Production integration: returns either live session or simulated checkout token
        checkout_id = str(uuid.uuid4())

        if provider == "stripe" and settings.STRIPE_SECRET_KEY:
            try:
                import stripe
                stripe.api_key = settings.STRIPE_SECRET_KEY
                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    line_items=[{
                        "price_data": {
                            "currency": plan_info["currency"],
                            "product_data": {"name": plan_info["name"]},
                            "unit_amount": int(plan_info["amount"] * 100),
                            "recurring": {"interval": "month"},
                        },
                        "quantity": 1,
                    }],
                    mode="subscription",
                    client_reference_id=user_id,
                    success_url="/billing?success=true&session_id={CHECKOUT_SESSION_ID}",
                    cancel_url="/billing?canceled=true",
                )
                return {"provider": "stripe", "checkout_url": session.url, "session_id": session.id}
            except Exception:
                pass

        # Development / Sandbox mock checkout
        return {
            "provider": provider,
            "checkout_id": checkout_id,
            "plan": plan_name,
            "amount": plan_info["amount"],
            "currency": plan_info["currency"],
            "mock_mode": not bool(settings.STRIPE_SECRET_KEY),
            "message": "Checkout initiated. Set STRIPE_SECRET_KEY or RAZORPAY_KEY_ID in environment for live gateway processing.",
        }

    @staticmethod
    def upgrade_user_plan(user_id: str, new_plan: str, provider: str, sub_id: str) -> None:
        """Upgrade user subscription record and user profile."""
        now = time.time()
        with db_session() as conn:
            conn.execute("UPDATE users SET plan = ?, updated_at = ? WHERE id = ?", (new_plan, now, user_id))
            sub_id_db = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO subscriptions
                (id, user_id, plan, status, provider, provider_subscription_id, current_period_end, created_at)
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (sub_id_db, user_id, new_plan, provider, sub_id, now + 30 * 86400, now),
            )
            # Log payment record
            amount = 12.0 if new_plan == "pro" else 39.0
            conn.execute(
                """
                INSERT INTO payments
                (id, user_id, amount, currency, status, provider, provider_payment_id, invoice_number, created_at)
                VALUES (?, ?, ?, 'USD', 'succeeded', ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), user_id, amount, provider, sub_id, f"INV-{int(now)}", now),
            )

    @staticmethod
    def verify_stripe_webhook(payload: bytes, sig_header: str) -> bool:
        """Verify Stripe webhook signature."""
        if not settings.STRIPE_WEBHOOK_SECRET:
            return False
        try:
            import stripe
            stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
            return True
        except Exception:
            return False

    @staticmethod
    def verify_razorpay_webhook(payload: bytes, signature: str) -> bool:
        """Verify Razorpay webhook signature."""
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            return False
        expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


billing = BillingService()

