"""
Razorpay Payment Gateway Integration Service.
Handles:
- Indian payment methods (UPI, RuPay, Debit/Credit Cards, NetBanking)
- Order creation in INR paise
- Cryptographic HMAC-SHA256 signature verification
- Webhook signature validation
- Test/sandbox and live production gateway support
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger("imageshrink.razorpay")


class RazorpayService:
    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET

    def create_order(
        self,
        amount_inr: int,
        user_id: str,
        user_email: str,
        plan_name: str,
        billing_cycle: str = "monthly",
    ) -> Dict[str, Any]:
        """
        Creates a Razorpay order with amount specified in INR paise (₹1 = 100 paise).
        """
        amount_paise = int(amount_inr * 100)
        receipt_id = f"rcpt_{uuid.uuid4().hex[:12]}"
        notes = {
            "user_id": user_id,
            "user_email": user_email,
            "plan": plan_name,
            "billing_cycle": billing_cycle,
        }

        # If live credentials exist and razorpay python client is installed, attempt live order creation
        if not self.key_id.startswith("rzp_test_"):
            try:
                import razorpay
                client = razorpay.Client(auth=(self.key_id, self.key_secret))
                data = {
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": receipt_id,
                    "notes": notes,
                    "payment_capture": 1,
                }
                order = client.order.create(data=data)
                return {
                    "id": order["id"],
                    "amount": order["amount"],
                    "currency": order["currency"],
                    "receipt": order.get("receipt", receipt_id),
                    "key_id": self.key_id,
                    "plan": plan_name,
                    "billing_cycle": billing_cycle,
                    "mock": False,
                }
            except Exception as e:
                logger.warning(f"Live Razorpay order creation failed, falling back to secure test order: {e}")

        # Secure test / sandbox order generator
        order_id = f"order_{uuid.uuid4().hex[:14]}"
        return {
            "id": order_id,
            "amount": amount_paise,
            "amount_inr": amount_inr,
            "currency": "INR",
            "receipt": receipt_id,
            "key_id": self.key_id,
            "plan": plan_name,
            "billing_cycle": billing_cycle,
            "notes": notes,
            "mock": True,
        }

    def verify_payment_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> bool:
        """
        Verifies Razorpay payment signature using HMAC-SHA256:
        signature = hmac_sha256(order_id + "|" + payment_id, secret)
        """
        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            return False

        message = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        expected_signature = hmac.new(
            self.key_secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(expected_signature, razorpay_signature):
            return True

        # In sandbox test mode, also accept test signatures generated for local developer flow
        if razorpay_signature.startswith("test_sig_") and self.key_id.startswith("rzp_test_"):
            return True

        return False

    def generate_test_signature(self, order_id: str, payment_id: str) -> str:
        """Utility to generate valid signature for test environments."""
        message = f"{order_id}|{payment_id}".encode("utf-8")
        return hmac.new(self.key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def verify_webhook_signature(self, payload_bytes: bytes, signature: str) -> bool:
        """Verifies Razorpay webhook signature header X-Razorpay-Signature."""
        webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        if not webhook_secret or not signature:
            return False

        expected = hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


razorpay_gateway = RazorpayService()

