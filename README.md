# ImageShrink Pro V2 — Intelligent Image Optimization Platform

[![CI/CD Pipeline](https://github.com/imageshrink/imageshrink-pro/actions/workflows/ci.yml/badge.svg)](https://github.com/imageshrink/imageshrink-pro/actions/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Pillow](https://img.shields.io/badge/Pillow-11.0+-blue.svg)](https://python-pillow.org)
[![License](https://img.shields.io/badge/license-Commercial-indigo.svg)]()

> **"Intelligent Image Optimization. Maximum Efficiency. Exceptional Quality."**

ImageShrink Pro V2 is a commercial-grade image optimization and conversion SaaS platform designed for photographers, digital agencies, e-commerce storefronts, and content creators handling large image libraries in bulk.

---

## 🌟 Key Features & Capabilities

- **Massive Batch Capacity**: Process batches of up to **500 images** concurrently, supporting up to **35 MB** per individual file.
- **Full Format Spectrum (Magic-Byte Binary Detection)**:
  - **JPEG**: Progressive encoding, MozJPEG-compatible Huffman optimization, chroma subsampling controls (4:4:4 vs 4:2:0), and EXIF preservation or stripping.
  - **PNG**: Zlib level 9 compression, palette optimization for $\le 256$ colors, alpha channel preservation, and pixel integrity verification.
  - **WebP**: Lossy and lossless modes, full alpha channel preservation, and animated WebP frame preservation.
  - **AVIF**: High-efficiency AV1 encoder with configurable quality and alpha preservation.
  - **GIF**: Animated GIF frame-by-frame optimization, frame timing, and loop count preservation.
  - **TIFF**: Multi-page archive preservation with Deflate and LZW compression.
  - **SVG**: XML minification, metadata stripping, script and XXE sanitization.
  - **BMP, HEIC, ICO**: Complete decompression, decoding, and optimization.
- **Three Optimization Modes**:
  1. **Lossless**: Bit-for-bit pixel integrity verification. Decoded pixel values remain identical.
  2. **Visually Lossless**: High-efficiency perceptual compression ($\text{SSIM} > 0.99$) preserving visual fidelity.
  3. **Custom**: Granular control over quality (1–100), max output size, resize constraints, and metadata.
- **Strict Rule 5 Enforcement**: When a candidate output is larger than the original, ImageShrink Pro **automatically retains the smaller original**. It never claims a file has been compressed if its size has not decreased.
- **Intelligent Format Conversion**: AI-guided recommendation engine that explains *why* a target format is recommended while strictly safeguarding transparency (never converting RGBA to JPEG without explicit authorization) and animations.
- **Results & Comparison Studio**:
  - Interactive before-and-after split slider with live handle drag.
  - Per-image perceptual metrics ($\text{SSIM}$ and $\text{PSNR}$ dB).
  - Streaming ZIP64 downloads without duplicate filename collisions.
  - CSV batch report generation.
- **Enterprise Security & Privacy**:
  - Magic-byte binary signature verification.
  - Decompression-bomb limits ($100\text{ MP}$ limit).
  - SVG script and event handler sanitization.
  - Automated 24-hour temporary file purge lifecycle.
  - Public API documentation endpoints (`/docs`, `/redoc`, `/openapi.json`) are completely hidden and disabled.

---

## 🔐 Dedicated Administrator Authentication & Access Control

ImageShrink Pro V2 includes a completely private, isolated administrator portal and access control system:

1. **Private Access Route**:
   - The administration dashboard is located exclusively at `/admin`.
   - Admin login is handled at `/admin/login`.
   - Admin routes and login buttons are **never** exposed in public navigation, user registration, or public client interfaces.
2. **Strict Server-Side Route Protection**:
   - Any unauthenticated visit to `/admin` or `/admin/*` is immediately redirected to `/admin/login`.
   - Administrative API calls without valid admin session tokens return HTTP `401 Unauthorized` or `403 Forbidden`.
   - Normal public user tokens cannot access any administrative endpoint.
3. **HTTP-Only Session Management**:
   - Admin authentication uses secure `HttpOnly` cookies (`SameSite=Lax`, `Secure` in production).
   - Raw session tokens are never stored in the database; only SHA-256 hashes are persisted.
   - Sessions expire after 4 hours or upon explicit logout.
4. **Brute-Force & Lockout Defenses**:
   - Login rate-limiting tracks attempts by both IP and username.
   - Temporary account lockout (15 minutes) is enforced after 5 consecutive failed attempts.
5. **Anti-CSRF Protection**:
   - Cryptographic HMAC-SHA256 tokens are enforced on all state-changing administrator actions.
6. **Credential Privacy**:
   - No default administrator credentials are hardcoded in frontend or application code.
   - Initial administrator accounts are provisioned via environment variables (`INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD`).
   - If no password is provided in `.env`, a cryptographically random one-time password is generated on initial server startup and saved to the server's private `storage/` directory for immediate rotation.
   - Passwords are encrypted with PBKDF2-HMAC-SHA256 (210,000 iterations).
   - Administrators can rotate their password directly from the admin dashboard with current password verification and strong complexity checks.
7. **Tamper-Evident Audit Logging**:
   - All logins, failed attempts, account lockouts, password changes, and administrative actions are logged in `admin_audit_logs`.
   - Passwords and session tokens are strictly redacted from logs.

---

## 🚀 Quick Start (Local Run)

### 1. Prerequisites
- Python 3.10+
- (Optional) Docker & Docker Compose for containerized deployment

### 2. Run with Python
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment (optional)
cp .env.example .env

# 3. Run the application
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** for the public image workspace.
- Access the private admin portal at **[http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)** (redirects to `/admin/login`).

---

## 🐳 Production Deployment (Docker Compose)

Deploy the complete production stack (FastAPI API, Celery Worker, PostgreSQL, Redis, and Nginx reverse proxy):

```bash
# Configure environment variables
cp .env.example .env

# Build and start all services
docker-compose up -d --build
```

---

## 🧪 Automated Testing

Run the automated test suites covering image optimization and admin authentication security:

```bash
# Run security and access control tests
pytest -v tests/test_admin_auth.py

# Run image optimization engine tests
pytest -v tests/test_image_engine.py
```
