"""
Pydantic Schemas for ImageShrink Pro V2 API.
Validation models for uploads, jobs, authentication, accounts, and billing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Auth Schemas
class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8)
    confirm_password: Optional[str] = None
    full_name: str = Field(default="", max_length=100)
    terms_accepted: bool = Field(default=False)
    privacy_accepted: bool = Field(default=False)


class UserLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str
    remember_me: bool = Field(default=False)


class EmailVerifyRequest(BaseModel):
    token: Optional[str] = None
    email: Optional[str] = None
    otp_code: Optional[str] = None


class ResendVerificationRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100)


class DeleteAccountRequest(BaseModel):
    password: str


class GoogleAuthCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]
    session_id: Optional[str] = None
    message: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    plan: str
    is_active: bool
    is_verified: bool = False
    created_at: float


# Optimization & Job Schemas
class OptimizationSettings(BaseModel):
    mode: str = Field(default="visual", description="lossless, visual, or custom")
    quality: int = Field(default=85, ge=1, le=100)
    target_format: Optional[str] = Field(default=None, description="original, JPEG, PNG, WEBP, or auto")
    keep_metadata: bool = False
    resize_max_width: Optional[int] = None
    resize_max_height: Optional[int] = None
    allow_discard_alpha: bool = False


class SingleImageResultSchema(BaseModel):
    image_id: str
    original_filename: str
    original_format: str
    original_size: int
    output_filename: Optional[str] = None
    output_format: Optional[str] = None
    output_size: Optional[int] = None
    bytes_saved: Optional[int] = 0
    percentage_saved: Optional[float] = 0.0
    ssim_score: Optional[float] = None
    psnr_score: Optional[float] = None
    status: str
    error_message: Optional[str] = None


class BatchJobResponse(BaseModel):
    batch_id: str
    total_files: int
    status: str
    mode: str
    created_at: float
    message: str


class BatchStatusResponse(BaseModel):
    batch_id: str
    name: str
    total_files: int
    processed_files: int
    failed_files: int
    total_original_size: int
    total_optimized_size: int
    status: str
    mode: str
    created_at: float
    completed_at: Optional[float] = None
    progress_percentage: float = 0.0


# Billing & Admin Schemas
class CheckoutRequest(BaseModel):
    plan: str = Field(..., description="pro, business, or premium")
    billing_cycle: str = Field(default="monthly", description="monthly or annual")
    provider: str = Field(default="razorpay", description="razorpay or stripe")


class RazorpayOrderRequest(BaseModel):
    plan: str = Field(..., description="pro, business, or premium")
    billing_cycle: str = Field(default="monthly", description="monthly or annual")


class RazorpayVerificationRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan: str
    billing_cycle: str = Field(default="monthly")


class UserStatusUpdateRequest(BaseModel):
    user_id: str
    is_active: bool
    is_admin: bool
    plan: str

