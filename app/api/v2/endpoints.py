"""
ImageShrink Pro V2 REST API Endpoints.
Implements all required specification endpoints:
- POST /api/v2/uploads
- POST /api/v2/optimization-jobs
- GET /api/v2/jobs/{job_id}
- GET /api/v2/jobs/{job_id}/results
- GET /api/v2/downloads/{job_id}
- DELETE /api/v2/jobs/{job_id}
- GET /api/v2/account/usage
- GET /api/v2/account/subscription
Plus Auth, Admin, Webhook, and CSV endpoints.
"""
from __future__ import annotations

import csv
import io
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.config import settings
from app.database import db_session
from app.dependencies import get_current_user, get_optional_user, rate_limiter_dependency, require_admin_user
from app.image_engine.detector import detect_format_from_bytes
from app.image_engine.validator import validate_image_data
from app.schemas import (
    BatchJobResponse,
    BatchStatusResponse,
    ChangePasswordRequest,
    CheckoutRequest,
    DeleteAccountRequest,
    EmailVerifyRequest,
    ForgotPasswordRequest,
    GoogleAuthCallbackRequest,
    RazorpayOrderRequest,
    RazorpayVerificationRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SingleImageResultSchema,
    TokenResponse,
    UpdateProfileRequest,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
    UserStatusUpdateRequest,
)
from app.security import (
    create_access_token,
    hash_password,
    sanitize_filename,
    verify_password,
)
from app.services.admin_service import admin_service
from app.services.auth_service import auth_service
from app.services.billing_service import billing
from app.services.google_oauth_service import google_oauth_service
from app.services.jobs import jobs_service
from app.services.razorpay_service import razorpay_gateway
from app.services.storage import storage
from app.services.subscription_service import subscription_service
from app.services.zip_service import create_zip_archive

router = APIRouter(prefix="/api/v2")


# ==========================================
# 1. AUTHENTICATION & ACCESS CONTROL ENDPOINTS
# ==========================================

@router.post("/auth/register", response_model=TokenResponse)
async def register(req: UserRegisterRequest, request: Request):
    """
    User Registration:
    - Creates unverified account
    - Validates strong password and confirmation
    - Requires Terms & Privacy acceptance
    - Provisions Free subscription tier (50 ops/month)
    - Dispatches verification link and 6-digit OTP via Google Gmail API
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "Unknown")

    confirm_pwd = req.confirm_password or req.password
    result = auth_service.register_user(
        email=req.email,
        password=req.password,
        confirm_password=confirm_pwd,
        full_name=req.full_name,
        terms_accepted=req.terms_accepted,
        privacy_accepted=req.privacy_accepted,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return result


@router.post("/auth/verify-email")
async def verify_email(req: EmailVerifyRequest, request: Request):
    """Verifies account via cryptographic URL token or 6-digit OTP code."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    return auth_service.verify_email(
        token=req.token,
        email=req.email,
        otp_code=req.otp_code,
        client_ip=client_ip,
    )


@router.post("/auth/resend-verification")
async def resend_verification(req: ResendVerificationRequest, request: Request):
    """Resends email verification token and OTP via Google Gmail API (rate limited to 1/min)."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    return auth_service.resend_verification(email=req.email, client_ip=client_ip)


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: UserLoginRequest, request: Request):
    """
    Authenticates user with email and password:
    - Brute-force protection & account lockout (15 min after 5 failed attempts)
    - Session tracking with optional extended 'Remember Me'
    - New-device login detection alert via Google Gmail API
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "Unknown")

    return auth_service.login_user(
        email=req.email,
        password=req.password,
        remember_me=req.remember_me,
        client_ip=client_ip,
        user_agent=user_agent,
    )


@router.post("/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request):
    """Sends time-limited (1h) password recovery link via Google Gmail API."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    return auth_service.forgot_password(email=req.email, client_ip=client_ip)


@router.post("/auth/reset-password")
async def reset_password(req: ResetPasswordRequest, request: Request):
    """Resets password, invalidates tokens and active sessions, sends confirmation email."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "Unknown")

    return auth_service.reset_password(
        token=req.token,
        new_password=req.new_password,
        confirm_password=req.confirm_password,
        client_ip=client_ip,
        user_agent=user_agent,
    )


@router.post("/auth/logout")
async def logout(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Logs out current session."""
    session_id = current_user.get("session_id")
    if session_id:
        auth_service.revoke_session(user_id=current_user["id"], session_id=session_id)
    return {"success": True, "message": "Logged out successfully."}


@router.post("/auth/logout-all")
async def logout_all(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Terminates all active sessions for this user across all devices."""
    return auth_service.logout_all_sessions(user_id=current_user["id"])


@router.get("/auth/google/url")
async def get_google_oauth_url():
    """Generates Google OAuth 2.0 URL for optional user sign-in."""
    url, state = google_oauth_service.generate_authorization_url()
    return {"url": url, "state": state, "configured": google_oauth_service.is_configured()}


@router.post("/auth/google/callback", response_model=TokenResponse)
async def google_oauth_callback(req: GoogleAuthCallbackRequest, request: Request):
    """Exchanges Google authorization code, links or creates user account, signs in user."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "Unknown")

    google_data = google_oauth_service.exchange_code_for_user_info(req.code)
    if not google_data or not google_data.get("email"):
        raise HTTPException(status_code=400, detail="Google authentication failed or was cancelled.")

    clean_email = google_data["email"].strip().lower()
    full_name = google_data.get("full_name", "")
    google_id = google_data.get("google_id")
    now = time.time()

    with db_session() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, email, full_name, plan, is_active FROM users WHERE email = ?", (clean_email,))
        existing = cur.fetchone()

        if existing:
            user_id = existing["id"]
            if not existing["is_active"]:
                raise HTTPException(status_code=403, detail="Account is suspended.")
            # Link Google ID and ensure verified
            cur.execute(
                "UPDATE users SET google_id = ?, is_verified = 1, email_verified_at = COALESCE(email_verified_at, ?), last_login = ?, last_login_ip = ?, updated_at = ? WHERE id = ?",
                (google_id, now, now, client_ip, now, user_id),
            )
            plan = existing["plan"]
        else:
            # Create new user via Google Sign-In (pre-verified)
            user_id = str(uuid.uuid4())
            random_pass = hash_password(secrets.token_urlsafe(32))
            cur.execute(
                """
                INSERT INTO users (
                    id, email, hashed_password, full_name, plan, is_active,
                    is_verified, email_verified_at, google_id, last_login,
                    last_login_ip, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'free', 1, 1, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, clean_email, random_pass, full_name, now, google_id, now, client_ip, now, now),
            )
            # Create initial Free Subscription
            free_limits = settings.PLANS["free"]
            cur.execute(
                """
                INSERT INTO subscriptions (
                    id, user_id, plan, status, billing_cycle, monthly_allowance,
                    used_quota, current_period_start, current_period_end,
                    cancel_at_period_end, provider, created_at, updated_at
                ) VALUES (?, ?, 'free', 'active', 'monthly', ?, 0, ?, ?, 0, 'google', ?, ?)
                """,
                (str(uuid.uuid4()), user_id, free_limits.monthly_allowance, now, now + 30 * 86400, now, now),
            )
            plan = "free"

        # Create session
        session_id = str(uuid.uuid4())
        session_token = generate_secure_token(32)
        cur.execute(
            """
            INSERT INTO user_sessions (id, user_id, token_hash, ip_address, user_agent, expires_at, is_remembered, last_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (session_id, user_id, hash_token(session_token), client_ip, user_agent, now + 30 * 86400, now, now),
        )

    access_token = create_access_token(
        {"sub": user_id, "email": clean_email, "plan": plan, "is_verified": True, "session_id": session_id},
        expires_delta_seconds=30 * 86400,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "session_id": session_id,
        "user": {
            "id": user_id,
            "email": clean_email,
            "full_name": full_name,
            "plan": plan,
            "is_verified": True,
        },
    }


@router.get("/auth/me", response_model=UserProfileResponse)
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Returns basic profile for currently authenticated user."""
    with db_session() as conn:
        cur = conn.cursor()
        cur.execute("SELECT created_at, is_verified FROM users WHERE id = ?", (current_user["id"],))
        row = cur.fetchone()
        created_at = row["created_at"] if row else time.time()
        is_verified = bool(row["is_verified"]) if row else False

    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "full_name": current_user.get("full_name", ""),
        "plan": current_user.get("plan", "free"),
        "is_active": bool(current_user.get("is_active", True)),
        "is_verified": is_verified,
        "created_at": created_at,
    }


# ==========================================
# 2. USER PROFILE & ACCOUNT SECURITY ENDPOINTS
# ==========================================

@router.get("/account/profile")
async def get_account_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Comprehensive account profile, active sessions, and security activity history."""
    return auth_service.get_profile_and_security_overview(user_id=current_user["id"])


@router.put("/account/profile")
async def update_profile(req: UpdateProfileRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Updates user display name."""
    return auth_service.update_profile(user_id=current_user["id"], full_name=req.full_name)


@router.post("/account/change-password")
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Changes password, revokes other sessions, and sends confirmation via Google Gmail."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "Unknown")

    return auth_service.change_password(
        user_id=current_user["id"],
        current_password=req.current_password,
        new_password=req.new_password,
        confirm_password=req.confirm_password,
        client_ip=client_ip,
        user_agent=user_agent,
        current_session_id=current_user.get("session_id"),
    )


@router.get("/account/sessions")
async def get_sessions(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Returns list of active login sessions."""
    overview = auth_service.get_profile_and_security_overview(user_id=current_user["id"])
    return {"sessions": overview["sessions"]}


@router.delete("/account/sessions/{session_id}")
async def revoke_session(session_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Revokes a specific session."""
    return auth_service.revoke_session(user_id=current_user["id"], session_id=session_id)


@router.delete("/account")
async def delete_account(req: DeleteAccountRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Permanently deletes account after password verification."""
    return auth_service.delete_account(user_id=current_user["id"], password=req.password)


# ==========================================
# 2. UPLOADS & OPTIMIZATION JOBS
# ==========================================

@router.post("/uploads")
async def upload_files(
    files: List[UploadFile] = File(...),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    POST /api/v2/uploads
    Uploads up to 500 images (each up to 35 MB) for processing.
    Validates file signatures, size, and user plan limits.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    user_id = current_user["id"] if current_user else None

    # Inspect all files before processing to extract sizes and detected formats
    file_payloads = []
    file_sizes = []
    file_formats = []
    total_batch_size = 0

    for idx, upload in enumerate(files):
        filename = sanitize_filename(upload.filename or f"image_{idx}")
        raw_bytes = await upload.read()
        file_size = len(raw_bytes)
        fmt, ext = detect_format_from_bytes(raw_bytes)
        file_payloads.append((filename, raw_bytes, file_size, fmt, ext))
        file_sizes.append(file_size)
        file_formats.append(fmt)
        total_batch_size += file_size
        await upload.close()

    # Enforce centralized subscription permissions, batch sizes, file sizes, and quotas
    allowed, reason, meta = subscription_service.verify_processing_permission(
        user_id=user_id,
        file_count=len(files),
        file_sizes=file_sizes,
        input_formats=file_formats,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)

    batch_id = str(uuid.uuid4())
    stored_images = []

    for filename, raw_bytes, file_size, fmt, ext in file_payloads:
        if fmt == "UNKNOWN":
            continue
        storage_path = storage.save_upload(batch_id, filename, raw_bytes)
        img_id = str(uuid.uuid4())
        stored_images.append((img_id, filename, fmt, file_size, storage_path, raw_bytes))

    if not stored_images:
        raise HTTPException(status_code=422, detail="No supported image files detected in upload.")

    now = time.time()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO upload_batches (id, user_id, name, total_files, status, created_at)
            VALUES (?, ?, ?, ?, 'uploaded', ?)
            """,
            (batch_id, user_id, f"Batch-{int(now)}", len(stored_images), now),
        )
        for img_id, filename, fmt, size, path, _ in stored_images:
            conn.execute(
                """
                INSERT INTO uploaded_images (id, batch_id, original_filename, original_format, original_size, storage_path, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'uploaded', ?)
                """,
                (img_id, batch_id, filename, fmt, size, path, now),
            )

    return {
        "batch_id": batch_id,
        "total_files": len(stored_images),
        "total_bytes": total_batch_size,
        "message": f"Successfully received {len(stored_images)} images.",
    }


@router.post("/optimization-jobs", response_model=BatchJobResponse)
async def submit_optimization_job(
    batch_id: Optional[str] = Form(None),
    mode: str = Form("visual"),
    quality: int = Form(85),
    target_format: Optional[str] = Form("original"),
    keep_metadata: bool = Form(False),
    resize_max_width: Optional[int] = Form(None),
    resize_max_height: Optional[int] = Form(None),
    target_size_kb: Optional[int] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """
    POST /api/v2/optimization-jobs
    Submits a batch optimization job.
    Supports either an existing batch_id from /uploads or direct multipart file submission.
    """
    user_id = current_user["id"] if current_user else None
    user_sub = subscription_service.get_user_subscription(user_id)
    plan_name = user_sub["plan"]

    # Enforce plan capabilities for advanced controls
    if target_size_kb and not user_sub.get("allow_target_file_size"):
        raise HTTPException(
            status_code=403,
            detail="Target file size controls require a Business (₹499/mo) or Premium (₹1,399/mo) plan.",
        )

    if (resize_max_width or resize_max_height) and not user_sub.get("allow_custom_dimensions"):
        raise HTTPException(
            status_code=403,
            detail="Custom dimensions and advanced resizing require a Business (₹499/mo) or Premium (₹1,399/mo) plan.",
        )

    # Direct multipart upload submission
    if files and len(files) > 0:
        file_payloads = []
        file_sizes = []
        file_formats = []

        for idx, upload in enumerate(files):
            filename = sanitize_filename(upload.filename or f"image_{idx}")
            raw_bytes = await upload.read()
            file_size = len(raw_bytes)
            fmt, ext = detect_format_from_bytes(raw_bytes)
            file_payloads.append((filename, raw_bytes, file_size, fmt, ext))
            file_sizes.append(file_size)
            file_formats.append(fmt)
            await upload.close()

        # Enforce batch count, file size, input format, target format, and monthly quota
        allowed, reason, meta = subscription_service.verify_processing_permission(
            user_id=user_id,
            file_count=len(files),
            file_sizes=file_sizes,
            input_formats=file_formats,
            target_format=target_format,
        )
        if not allowed:
            raise HTTPException(status_code=403, detail=reason)

        new_batch_id = str(uuid.uuid4())
        files_data: List[Tuple[str, str, bytes]] = []
        now = time.time()

        settings_dict = {
            "quality": quality,
            "target_format": target_format,
            "keep_metadata": keep_metadata,
            "resize_max_width": resize_max_width,
            "resize_max_height": resize_max_height,
            "target_size_kb": target_size_kb,
        }

        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO upload_batches (id, user_id, name, total_files, status, mode, settings_json, created_at)
                VALUES (?, ?, ?, ?, 'processing', ?, ?, ?)
                """,
                (new_batch_id, user_id, f"Batch-{int(now)}", len(files), mode, json.dumps(settings_dict), now),
            )

            for filename, raw_bytes, file_size, fmt, ext in file_payloads:
                if fmt == "UNKNOWN":
                    continue
                storage_path = storage.save_upload(new_batch_id, filename, raw_bytes)
                img_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO uploaded_images (id, batch_id, original_filename, original_format, original_size, storage_path, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (img_id, new_batch_id, filename, fmt, file_size, storage_path, now),
                )
                files_data.append((img_id, filename, raw_bytes))

        if not files_data:
            raise HTTPException(status_code=422, detail="No valid images were provided.")

        jobs_service.submit_batch_processing(
            new_batch_id,
            files_data,
            mode,
            target_format,
            quality,
            keep_metadata=keep_metadata,
            resize_max_width=resize_max_width,
            resize_max_height=resize_max_height,
            target_size_kb=target_size_kb,
        )
        return {
            "batch_id": new_batch_id,
            "total_files": len(files_data),
            "status": "processing",
            "mode": mode,
            "created_at": now,
            "message": f"Optimization started for {len(files_data)} images.",
        }

    # Execution of pre-uploaded batch
    if not batch_id:
        raise HTTPException(status_code=400, detail="Must provide either files or an existing batch_id.")

    with db_session() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, original_filename, original_format, original_size, storage_path FROM uploaded_images WHERE batch_id = ?", (batch_id,))
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Batch ID not found or has no files.")

        files_data = []
        file_sizes = []
        file_formats = []
        for r in rows:
            raw = storage.get_file_bytes(r["storage_path"])
            if raw:
                files_data.append((r["id"], r["original_filename"], raw))
                file_sizes.append(r["original_size"])
                file_formats.append(r["original_format"])

        # Validate target format and remaining quota
        allowed, reason, meta = subscription_service.verify_processing_permission(
            user_id=user_id,
            file_count=len(files_data),
            file_sizes=file_sizes,
            input_formats=file_formats,
            target_format=target_format,
        )
        if not allowed:
            raise HTTPException(status_code=403, detail=reason)

        conn.execute("UPDATE upload_batches SET status = 'processing', mode = ? WHERE id = ?", (mode, batch_id))

    jobs_service.submit_batch_processing(
        batch_id,
        files_data,
        mode,
        target_format,
        quality,
        keep_metadata=keep_metadata,
        resize_max_width=resize_max_width,
        resize_max_height=resize_max_height,
        target_size_kb=target_size_kb,
    )
    return {
        "batch_id": batch_id,
        "total_files": len(files_data),
        "status": "processing",
        "mode": mode,
        "created_at": time.time(),
        "message": f"Optimization started for batch {batch_id}.",
    }


@router.get("/jobs/{job_id}", response_model=BatchStatusResponse)
async def get_job_status(job_id: str):
    """
    GET /api/v2/jobs/{job_id}
    Retrieves real-time processing status and progress percentage.
    """
    status_data = jobs_service.get_batch_status(job_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Optimization job not found.")

    total = status_data["total_files"]
    processed = status_data["processed_files"] + status_data["failed_files"]
    pct = round((processed / total * 100.0), 1) if total > 0 else 0.0

    return {
        "batch_id": status_data["id"],
        "name": status_data["name"],
        "total_files": status_data["total_files"],
        "processed_files": status_data["processed_files"],
        "failed_files": status_data["failed_files"],
        "total_original_size": status_data["total_original_size"],
        "total_optimized_size": status_data["total_optimized_size"],
        "status": status_data["status"],
        "mode": status_data["mode"],
        "created_at": status_data["created_at"],
        "completed_at": status_data.get("completed_at"),
        "progress_percentage": min(100.0, pct),
    }


@router.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str):
    """
    GET /api/v2/jobs/{job_id}/results
    Returns per-file before/after comparison results, savings, and metrics.
    """
    results = jobs_service.get_batch_results(job_id)
    if not results:
        status_data = jobs_service.get_batch_status(job_id)
        if not status_data:
            raise HTTPException(status_code=404, detail="Job not found.")
        return {"batch_id": job_id, "results": [], "status": status_data["status"]}

    return {
        "batch_id": job_id,
        "results": results,
        "total": len(results),
    }


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    """
    DELETE /api/v2/jobs/{job_id}
    Deletes batch records and frees storage.
    """
    with db_session() as conn:
        conn.execute("DELETE FROM upload_batches WHERE id = ?", (job_id,))
    return {"message": f"Job {job_id} deleted successfully."}


# ==========================================
# 3. DOWNLOAD INFRASTRUCTURE
# ==========================================

@router.get("/downloads/{job_id}")
async def download_batch_zip(job_id: str):
    """
    GET /api/v2/downloads/{job_id}
    Streams a full ZIP64 archive of all optimized images in the batch.
    """
    results = jobs_service.get_batch_results(job_id)
    if not results:
        raise HTTPException(status_code=404, detail="No files found for this job.")

    files_to_pack: List[Tuple[str, bytes]] = []
    for r in results:
        if r.get("output_filename") and r.get("storage_path"):
            b = storage.get_file_bytes(r["storage_path"])
            if b:
                files_to_pack.append((r["output_filename"], b))

    if not files_to_pack:
        raise HTTPException(status_code=404, detail="No completed images available for download.")

    zip_bytes = create_zip_archive(files_to_pack)
    filename = f"imageshrink_pro_{job_id[:8]}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/downloads/{job_id}/file/{image_id}")
async def download_single_image(job_id: str, image_id: str):
    """Download a single optimized image."""
    with db_session() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT output_filename, storage_path, output_format FROM optimization_results WHERE image_id = ? AND batch_id = ?",
            (image_id, job_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File result not found.")

        data = storage.get_file_bytes(row["storage_path"])
        if not data:
            raise HTTPException(status_code=404, detail="Optimized file missing on storage.")

        mime = f"image/{row['output_format'].lower()}"
        return Response(
            content=data,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{row["output_filename"]}"'},
        )


@router.get("/downloads/{job_id}/csv")
async def download_batch_csv(job_id: str):
    """Generate and return a batch optimization report in CSV format."""
    results = jobs_service.get_batch_results(job_id)
    if not results:
        raise HTTPException(status_code=404, detail="No results found.")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Original Filename",
        "Original Format",
        "Original Size (Bytes)",
        "Output Filename",
        "Output Format",
        "Output Size (Bytes)",
        "Bytes Saved",
        "Percentage Saved (%)",
        "SSIM Score",
        "PSNR Score (dB)",
        "Status",
    ])

    for r in results:
        writer.writerow([
            r.get("original_filename", ""),
            r.get("original_format", ""),
            r.get("original_size", 0),
            r.get("output_filename", ""),
            r.get("output_format", ""),
            r.get("output_size", 0),
            r.get("bytes_saved", 0),
            r.get("percentage_saved", 0.0),
            r.get("ssim_score", ""),
            r.get("psnr_score", ""),
            r.get("processing_status", ""),
        ])

    csv_data = output.getvalue().encode("utf-8")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="imageshrink_report_{job_id[:8]}.csv"'},
    )


# ==========================================
# 4. PRICING, ACCOUNT & SUBSCRIPTION ENDPOINTS
# ==========================================

@router.get("/pricing/plans")
async def get_pricing_plans():
    """
    Returns all 4 official subscription tiers with exact INR pricing,
    annual discounts, quotas, batch limits, and format matrix.
    """
    plans_out = {}
    for key, p in settings.PLANS.items():
        plans_out[key] = {
            "key": key,
            "name": p.name,
            "price_monthly_inr": p.price_monthly_inr,
            "price_annual_inr": p.price_annual_inr,
            "annual_discount_percent": 17 if p.price_monthly_inr > 0 else 0,
            "monthly_allowance": p.monthly_allowance,
            "max_batch_size": p.max_batch_size,
            "max_file_size_mb": p.max_file_size_mb,
            "allowed_formats": p.allowed_formats,
            "allowed_modes": p.allowed_modes,
            "priority_level": p.priority_level,
            "allow_api_access": p.allow_api_access,
            "allow_bulk_conversion": p.allow_bulk_conversion,
            "allow_custom_dimensions": p.allow_custom_dimensions,
            "allow_target_file_size": p.allow_target_file_size,
            "allow_saved_presets": p.allow_saved_presets,
            "allow_reports": p.allow_reports,
            "ad_free": p.ad_free,
        }
    return {
        "plans": plans_out,
        "format_matrix": settings.FORMAT_PERMISSIONS,
        "currency": "INR",
        "currency_symbol": "₹",
    }


@router.get("/account/subscription")
async def get_account_subscription(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    GET /api/v2/account/subscription
    Returns complete real-time subscription details, monthly allowance,
    used quota, remaining quota, renewal date, and feature permissions.
    """
    user_id = current_user["id"]
    return subscription_service.get_user_subscription(user_id)


@router.get("/account/usage")
async def get_account_usage(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    GET /api/v2/account/usage
    Returns processed image count, total bytes saved, and quota progress.
    """
    user_id = current_user["id"]
    sub = subscription_service.get_user_subscription(user_id)

    with db_session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                COUNT(*) as total_batches,
                SUM(processed_files) as total_processed_images,
                SUM(total_original_size) as orig_size,
                SUM(total_optimized_size) as opt_size
            FROM upload_batches 
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
        orig = row["orig_size"] or 0
        opt = row["opt_size"] or 0
        saved = max(0, orig - opt)

    return {
        "user_id": user_id,
        "plan": sub["plan"],
        "plan_name": sub["plan_name"],
        "monthly_allowance": sub["monthly_allowance"],
        "used_quota": sub["used_quota"],
        "remaining_quota": sub["remaining_quota"],
        "usage_percentage": sub["usage_percentage"],
        "total_batches": row["total_batches"] or 0,
        "total_images_processed": row["total_processed_images"] or 0,
        "original_bytes": orig,
        "optimized_bytes": opt,
        "saved_bytes": saved,
        "percentage_saved": round((saved / orig * 100), 2) if orig > 0 else 0.0,
        "max_batch_size": sub["max_batch_size"],
        "max_file_size_mb": sub["max_file_size_mb"],
        "allowed_formats": sub["allowed_formats"],
        "renewal_date": sub["current_period_end"],
    }


@router.get("/account/invoices")
async def get_account_invoices(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Returns invoice and payment history."""
    return subscription_service.get_invoices(current_user["id"])


@router.get("/account/history")
async def get_account_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Returns recent auditable processing history."""
    return subscription_service.get_processing_history(current_user["id"], limit=50)


# ==========================================
# 5. RAZORPAY BILLING & CHECKOUT
# ==========================================

@router.post("/billing/create-order")
async def create_razorpay_order(
    req: RazorpayOrderRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Creates a Razorpay order in INR for the requested plan and billing cycle.
    """
    plan_key = req.plan.lower()
    if plan_key not in settings.PLANS:
        raise HTTPException(status_code=400, detail="Invalid subscription plan.")

    plan_limits = settings.PLANS[plan_key]
    is_annual = req.billing_cycle.lower() == "annual"
    amount_inr = plan_limits.price_annual_inr if is_annual else plan_limits.price_monthly_inr

    # Free plan requires no payment gateway order
    if amount_inr == 0:
        res = subscription_service.activate_subscription(
            user_id=current_user["id"],
            plan_name="free",
            billing_cycle="monthly",
            provider="system",
        )
        return {"free_activation": True, "subscription": res}

    order_data = razorpay_gateway.create_order(
        amount_inr=amount_inr,
        user_id=current_user["id"],
        user_email=current_user["email"],
        plan_name=plan_key,
        billing_cycle=req.billing_cycle,
    )
    return order_data


@router.post("/billing/verify-payment")
async def verify_razorpay_payment(
    req: RazorpayVerificationRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Verifies Razorpay HMAC-SHA256 signature and activates the subscription.
    Generates a formal invoice with 18% GST.
    """
    is_valid = razorpay_gateway.verify_payment_signature(
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_signature=req.razorpay_signature,
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Payment signature verification failed. Untrusted payment attempt.")

    # Activate plan atomically
    activation = subscription_service.activate_subscription(
        user_id=current_user["id"],
        plan_name=req.plan,
        billing_cycle=req.billing_cycle,
        provider="razorpay",
        provider_payment_id=req.razorpay_payment_id,
        provider_order_id=req.razorpay_order_id,
    )

    return {
        "status": "success",
        "message": f"Successfully activated {req.plan.upper()} subscription!",
        "activation": activation,
    }


@router.post("/billing/cancel")
async def cancel_subscription(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Cancels subscription renewal at period end.
    """
    return subscription_service.cancel_subscription(current_user["id"])


# Backward compatible checkout route
@router.post("/billing/checkout")
async def legacy_checkout(req: CheckoutRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    if req.provider == "razorpay":
        plan_key = req.plan.lower()
        plan_limits = settings.PLANS.get(plan_key, settings.PLANS["pro"])
        amount_inr = plan_limits.price_annual_inr if req.billing_cycle == "annual" else plan_limits.price_monthly_inr
        return razorpay_gateway.create_order(
            amount_inr=amount_inr,
            user_id=current_user["id"],
            user_email=current_user["email"],
            plan_name=plan_key,
            billing_cycle=req.billing_cycle,
        )
    return billing.create_checkout_session(current_user["id"], req.plan, req.provider)


# ==========================================
# 6. PAYMENT WEBHOOKS
# ==========================================

@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: Optional[str] = Header(None)):
    payload = await request.body()
    if settings.STRIPE_WEBHOOK_SECRET and stripe_signature:
        if not billing.verify_stripe_webhook(payload, stripe_signature):
            raise HTTPException(status_code=400, detail="Invalid signature.")
    return {"status": "received"}


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, x_razorpay_signature: Optional[str] = Header(None)):
    payload = await request.body()
    if settings.RAZORPAY_WEBHOOK_SECRET and x_razorpay_signature:
        if not razorpay_gateway.verify_webhook_signature(payload, x_razorpay_signature):
            raise HTTPException(status_code=400, detail="Invalid webhook signature.")
    return {"status": "received"}

