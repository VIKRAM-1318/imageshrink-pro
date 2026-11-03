"""
ImageShrink Pro V2 Main Application Server.
Autonomous SaaS for Intelligent Bulk Image Optimization.
Integrates V2 REST APIs, high-performance background processing,
lossless and visual-lossless engines, security headers, modern UI,
and private Administrator Access Control.
"""
from __future__ import annotations

import io
import os
import time
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.admin_routes import admin_router
from app.api.v2.endpoints import router as v2_router
from app.config import BASE_DIR, STORAGE_DIR, settings
from app.database import init_db
from app.image_engine.engine import optimize_single_image
from app.services.jobs import jobs_service
from app.services.storage import storage
from app.services.zip_service import create_zip_archive

# Initialize FastAPI with API documentation completely hidden as requested
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Professional Online SaaS Platform for Intelligent Image Optimization and Format Conversion.",
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None,
)

# CORS Middleware (configurable allowed origins)
allowed_origins_env = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
allowed_origins = allowed_origins_env if allowed_origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Enforce strict production security headers on all responses."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate" if request.url.path.startswith("/admin") else "public, max-age=3600"
    return response


# Include Admin Router (Private isolated portal)
app.include_router(admin_router)

# Include Versioned REST API
app.include_router(v2_router)

# Mount static assets directory
static_dir = BASE_DIR / "app" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
def on_startup():
    """Initialize SQLite/Postgres schemas, seed default admin & promo codes, and purge stale temp jobs."""
    init_db()
    storage.cleanup_old_files(max_age_seconds=settings.JOB_TTL_SECONDS)


@app.get("/", response_class=HTMLResponse)
def root_view():
    """Serves the public ImageShrink Pro V2 application."""
    index_path = BASE_DIR / "app" / "templates" / "index.html"
    if index_path.is_file():
        return index_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>ImageShrink Pro V2</h1>")


@app.get("/privacy", response_class=HTMLResponse)
@app.get("/privacy.html", response_class=HTMLResponse)
def privacy_policy_view():
    """Serves the comprehensive Privacy Policy document."""
    privacy_path = BASE_DIR / "app" / "templates" / "privacy.html"
    if privacy_path.is_file():
        return privacy_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>Privacy Policy</h1><p>ImageShrink Pro Privacy Policy.</p>")


@app.get("/terms", response_class=HTMLResponse)
@app.get("/terms.html", response_class=HTMLResponse)
def terms_of_service_view():
    """Serves the comprehensive Terms of Service document."""
    terms_path = BASE_DIR / "app" / "templates" / "terms.html"
    if terms_path.is_file():
        return terms_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>Terms of Service</h1><p>ImageShrink Pro Terms of Service.</p>")


@app.get("/verify-email", response_class=HTMLResponse)
def verify_email_page(token: Optional[str] = None):
    """Handles direct email verification links from Gmail messages."""
    if token:
        try:
            from app.services.auth_service import auth_service
            auth_service.verify_email(token=token)
            message = "Your email address has been successfully verified! You now have full access to ImageShrink Pro."
            status_badge = "Email Verified Successfully"
            is_success = True
        except Exception as e:
            message = f"{e.detail if hasattr(e, 'detail') else str(e)}"
            status_badge = "Verification Link Expired or Invalid"
            is_success = False
    else:
        message = "No verification token was provided in the link."
        status_badge = "Invalid Verification Link"
        is_success = False

    color = "#10b981" if is_success else "#ef4444"
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{status_badge} - ImageShrink Pro</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-950 text-white min-h-screen flex items-center justify-center p-4">
  <div class="max-w-md w-full bg-zinc-900 border border-zinc-800 rounded-2xl p-8 text-center space-y-4 shadow-2xl">
    <div class="w-16 h-16 mx-auto rounded-full flex items-center justify-center" style="background-color: {color}20; color: {color};">
      <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        { '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>' if is_success else '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>' }
      </svg>
    </div>
    <h2 class="text-2xl font-bold tracking-tight text-white">{status_badge}</h2>
    <p class="text-sm text-zinc-400 leading-relaxed">{message}</p>
    <div class="pt-4">
      <a href="/#workspace" class="inline-block w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl text-sm transition">
        Continue to ImageShrink Pro &rarr;
      </a>
    </div>
  </div>
</body>
</html>""")


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


# Backward Compatibility Route for V1 Clients
@app.post("/api/optimize")
async def legacy_optimize(
    files: List[UploadFile] = File(...),
    mode: Literal["lossless", "visual", "custom"] = Form("visual"),
    quality: int = Form(90),
):
    """Preserves backward compatibility with MVP endpoints."""
    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one image.")
    if len(files) > settings.MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"Maximum batch size is {settings.MAX_BATCH_FILES} images.")

    import uuid
    batch_id = str(uuid.uuid4())
    results = []
    files_to_pack = []
    total_before = total_after = 0

    for idx, upload in enumerate(files):
        name = upload.filename or f"image_{idx}"
        raw_bytes = await upload.read()
        await upload.close()
        if len(raw_bytes) > settings.MAX_FILE_BYTES:
            results.append({"name": name, "status": "Failed", "error": "Exceeds 35 MB limit"})
            continue
        try:
            res = optimize_single_image(raw_bytes, name, mode=mode, quality=quality)
            total_before += res["original_size"]
            total_after += res["optimized_size"]
            files_to_pack.append((res["output_filename"], res["data"]))
            results.append({
                "name": name,
                "output": res["output_filename"],
                "status": "Completed",
                "before": res["original_size"],
                "after": res["optimized_size"],
                "saved": res["bytes_saved"],
                "percent": res["percentage_saved"],
                "format": res["output_format"],
            })
        except Exception as exc:
            results.append({"name": name, "status": "Failed", "error": str(exc)})

    # Generate ZIP
    zip_bytes = create_zip_archive(files_to_pack) if files_to_pack else b""
    zip_path = STORAGE_DIR / f"{batch_id}.zip"
    if zip_bytes:
        zip_path.write_bytes(zip_bytes)

    return {
        "job_id": batch_id,
        "results": results,
        "summary": {
            "processed": len(files_to_pack),
            "failed": len(files) - len(files_to_pack),
            "before": total_before,
            "after": total_after,
            "saved": max(0, total_before - total_after),
            "percent": round(((total_before - total_after) / total_before) * 100, 1) if total_before else 0,
        },
        "download_url": f"/api/v2/downloads/{batch_id}" if files_to_pack else "",
    }
