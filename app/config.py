"""
ImageShrink Pro V2 Configuration Module.
Supports environment variables, production security settings, and plan quotas.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

UPLOADS_DIR = STORAGE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

OPTIMIZED_DIR = STORAGE_DIR / "optimized"
OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)

JOBS_DIR = STORAGE_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


class PlanLimits(BaseModel):
    name: str
    price_monthly_inr: int
    price_annual_inr: int
    monthly_allowance: int  # Monthly image processing quota
    max_batch_size: int
    max_file_size_mb: int
    allowed_formats: List[str]
    allowed_modes: List[str]
    priority_level: int
    allow_api_access: bool
    allow_bulk_conversion: bool
    allow_custom_dimensions: bool
    allow_target_file_size: bool
    allow_saved_presets: bool
    allow_reports: bool
    ad_free: bool


class Settings(BaseModel):
    APP_NAME: str = "ImageShrink Pro"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "imageshrink-pro-super-secret-production-key-v2-32b")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Public API Documentation disabled completely
    ENABLE_API_DOCS: bool = False

    # Admin Portal Security Configuration
    ADMIN_PATH_PREFIX: str = "/admin"
    ADMIN_SESSION_COOKIE_NAME: str = "isp_admin_session"
    ADMIN_CSRF_COOKIE_NAME: str = "isp_admin_csrf"
    ADMIN_SESSION_EXPIRE_HOURS: int = 4
    ADMIN_MAX_LOGIN_ATTEMPTS: int = 5
    ADMIN_LOCKOUT_MINUTES: int = 15
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() in ("true", "1")

    # Initial Administrator Provisioning via Environment Variables
    INITIAL_ADMIN_EMAIL: str = os.getenv("INITIAL_ADMIN_EMAIL", "admin@imageshrink.internal")
    INITIAL_ADMIN_PASSWORD: Optional[str] = os.getenv("INITIAL_ADMIN_PASSWORD", None)
    ADMIN_SECRET_KEY: str = os.getenv("ADMIN_SECRET_KEY", "imageshrink-admin-guard-super-secret-salt-2026")

    # Limits as per non-negotiable requirements
    MAX_FILE_BYTES: int = 35 * 1024 * 1024  # 35 MB strictly enforced
    MAX_BATCH_FILES: int = 1000  # Support batches of up to 1000 images for Premium
    MAX_PIXEL_COUNT: int = 100_000_000  # 100 Megapixels decompression bomb protection
    JOB_TTL_SECONDS: int = 24 * 3600  # 24 hours temporary file retention

    # Database & Cache
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'imageshrink_v2.db'}")
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)

    # Cloud Storage (AWS S3 / Cloudflare R2 / MinIO)
    S3_ENDPOINT_URL: Optional[str] = os.getenv("S3_ENDPOINT_URL", None)
    S3_ACCESS_KEY: Optional[str] = os.getenv("S3_ACCESS_KEY", None)
    S3_SECRET_KEY: Optional[str] = os.getenv("S3_SECRET_KEY", None)
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "imageshrink-production")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")
    USE_S3_STORAGE: bool = os.getenv("USE_S3_STORAGE", "false").lower() in ("true", "1")

    # Google Gmail API for Transactional Authentication Emails
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8000")
    GMAIL_CLIENT_ID: Optional[str] = os.getenv("GMAIL_CLIENT_ID", None)
    GMAIL_CLIENT_SECRET: Optional[str] = os.getenv("GMAIL_CLIENT_SECRET", None)
    GMAIL_REFRESH_TOKEN: Optional[str] = os.getenv("GMAIL_REFRESH_TOKEN", None)
    GMAIL_SENDER_EMAIL: str = os.getenv("GMAIL_SENDER_EMAIL", "notifications@imageshrink.com")
    GMAIL_SENDER_NAME: str = os.getenv("GMAIL_SENDER_NAME", "ImageShrink Pro Security")
    GMAIL_TOKEN_ENCRYPTION_KEY: Optional[str] = os.getenv("GMAIL_TOKEN_ENCRYPTION_KEY", None)
    GMAIL_DAILY_QUOTA_LIMIT: int = int(os.getenv("GMAIL_DAILY_QUOTA_LIMIT", "500"))

    # Google Sign-In (User Authentication via OAuth 2.0)
    GOOGLE_AUTH_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_AUTH_CLIENT_ID", None)
    GOOGLE_AUTH_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_AUTH_CLIENT_SECRET", None)
    GOOGLE_AUTH_REDIRECT_URI: str = os.getenv("GOOGLE_AUTH_REDIRECT_URI", "http://localhost:8000/api/v2/auth/google/callback")

    # Payment Gateways (Razorpay primary in INR, Stripe secondary)
    RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "rzp_test_imageshrink2026")
    RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "sec_rzp_imageshrink_secret_2026")
    RAZORPAY_WEBHOOK_SECRET: Optional[str] = os.getenv("RAZORPAY_WEBHOOK_SECRET", "whsec_rzp_webhook_secret_2026")

    STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY", None)
    STRIPE_PUBLISHABLE_KEY: Optional[str] = os.getenv("STRIPE_PUBLISHABLE_KEY", None)
    STRIPE_WEBHOOK_SECRET: Optional[str] = os.getenv("STRIPE_WEBHOOK_SECRET", None)

    # Allowed input extensions across the system
    ALLOWED_EXTENSIONS: set[str] = {
        ".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif",
        ".tif", ".tiff", ".bmp", ".heic", ".heif", ".svg", ".ico"
    }

    # Subscription Plans & Exact INR Pricing as per specifications
    PLANS: Dict[str, PlanLimits] = {
        "free": PlanLimits(
            name="Free",
            price_monthly_inr=0,
            price_annual_inr=0,
            monthly_allowance=50,
            max_batch_size=10,
            max_file_size_mb=10,
            allowed_formats=["jpg", "jpeg", "png"],
            allowed_modes=["lossless", "visual"],
            priority_level=1,
            allow_api_access=False,
            allow_bulk_conversion=False,
            allow_custom_dimensions=False,
            allow_target_file_size=False,
            allow_saved_presets=False,
            allow_reports=False,
            ad_free=False,
        ),
        "pro": PlanLimits(
            name="Pro",
            price_monthly_inr=249,
            price_annual_inr=2490,  # 2 months free discount
            monthly_allowance=2000,
            max_batch_size=100,
            max_file_size_mb=35,
            allowed_formats=["jpg", "jpeg", "png", "webp", "gif", "bmp"],
            allowed_modes=["lossless", "visual", "custom"],
            priority_level=2,
            allow_api_access=False,
            allow_bulk_conversion=True,
            allow_custom_dimensions=False,
            allow_target_file_size=False,
            allow_saved_presets=False,
            allow_reports=False,
            ad_free=True,
        ),
        "business": PlanLimits(
            name="Business",
            price_monthly_inr=499,
            price_annual_inr=4990,  # 2 months free discount
            monthly_allowance=10000,
            max_batch_size=500,
            max_file_size_mb=35,
            allowed_formats=["jpg", "jpeg", "png", "webp", "avif", "gif", "bmp", "tif", "tiff", "heic", "heif"],
            allowed_modes=["lossless", "visual", "custom"],
            priority_level=3,
            allow_api_access=False,
            allow_bulk_conversion=True,
            allow_custom_dimensions=True,
            allow_target_file_size=True,
            allow_saved_presets=False,
            allow_reports=True,
            ad_free=True,
        ),
        "premium": PlanLimits(
            name="Premium",
            price_monthly_inr=1399,
            price_annual_inr=13990,  # 2 months free discount
            monthly_allowance=50000,
            max_batch_size=1000,
            max_file_size_mb=35,
            allowed_formats=["jpg", "jpeg", "png", "webp", "avif", "gif", "bmp", "tif", "tiff", "heic", "heif", "ico", "svg"],
            allowed_modes=["lossless", "visual", "custom"],
            priority_level=4,
            allow_api_access=True,
            allow_bulk_conversion=True,
            allow_custom_dimensions=True,
            allow_target_file_size=True,
            allow_saved_presets=True,
            allow_reports=True,
            ad_free=True,
        ),
    }

    # Centralized Format Permissions Matrix
    FORMAT_PERMISSIONS: Dict[str, str] = {
        "jpg": "free",
        "jpeg": "free",
        "png": "free",
        "webp": "pro",
        "gif": "pro",
        "bmp": "pro",
        "avif": "business",
        "tif": "business",
        "tiff": "business",
        "heic": "business",
        "heif": "business",
        "ico": "premium",
        "svg": "premium",
    }


def get_plan_hierarchy(plan: str) -> int:
    """Numerical hierarchy for plan upgrade/downgrade checks."""
    levels = {"free": 0, "pro": 1, "business": 2, "premium": 3}
    return levels.get(plan.lower(), 0)


def is_format_allowed_for_plan(format_name: str, plan_name: str) -> bool:
    """Checks whether a given image format is permitted under the specified subscription tier."""
    clean_fmt = format_name.lower().lstrip(".")
    if clean_fmt == "jpg":
        clean_fmt = "jpeg"
    required_plan = settings.FORMAT_PERMISSIONS.get(clean_fmt)
    if not required_plan:
        return False
    return get_plan_hierarchy(plan_name) >= get_plan_hierarchy(required_plan)


def get_required_plan_for_format(format_name: str) -> str:
    """Returns the minimum plan name required to access a specific format."""
    clean_fmt = format_name.lower().lstrip(".")
    if clean_fmt == "jpg":
        clean_fmt = "jpeg"
    return settings.FORMAT_PERMISSIONS.get(clean_fmt, "premium").capitalize()


settings = Settings()
