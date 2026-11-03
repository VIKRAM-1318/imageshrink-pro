"""
Automated Test Suite for ImageShrink Pro V2.
Tests format detection, 35 MB limit enforcement, SVG sanitization,
lossless pixel integrity, Rule 5 size retention, and security tokens.
"""
import io
from PIL import Image, ImageDraw

from app.config import settings
from app.image_engine.comparator import compute_metrics
from app.image_engine.converter import recommend_best_format, convert_image, ConversionError
from app.image_engine.detector import detect_format_from_bytes
from app.image_engine.engine import optimize_single_image
from app.image_engine.jpeg import optimize_jpeg
from app.image_engine.png import optimize_png, verify_pixel_integrity
from app.image_engine.svg import optimize_svg
from app.image_engine.validator import validate_image_data, sanitize_svg_data, ImageValidationError
from app.security import hash_password, verify_password, create_access_token, decode_access_token
from app.services.zip_service import create_zip_archive


def create_sample_png(size=(100, 100), has_alpha=False) -> bytes:
    img = Image.new("RGBA" if has_alpha else "RGB", size, (255, 0, 0, 128 if has_alpha else 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 50, 50], fill=(0, 255, 0, 255))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def create_sample_jpeg(size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, (50, 100, 150))
    draw = ImageDraw.Draw(img)
    draw.line([0, 0, 100, 100], fill=(255, 255, 255), width=3)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=95)
    return out.getvalue()


def test_magic_bytes_detection():
    png_bytes = create_sample_png()
    fmt, ext = detect_format_from_bytes(png_bytes)
    assert fmt == "PNG"
    assert ext == ".png"

    jpeg_bytes = create_sample_jpeg()
    fmt, ext = detect_format_from_bytes(jpeg_bytes)
    assert fmt == "JPEG"
    assert ext == ".jpg"

    svg_data = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect/></svg>'
    fmt, ext = detect_format_from_bytes(svg_data)
    assert fmt == "SVG"
    assert ext == ".svg"


def test_svg_sanitization():
    malicious_svg = b"""<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" onload="alert('xss')">
        <script>alert('pwned')</script>
        <circle cx="50" cy="50" r="40" stroke="green" stroke-width="4" fill="yellow" onclick="steal()"/>
    </svg>"""

    sanitized = sanitize_svg_data(malicious_svg)
    text = sanitized.decode("utf-8")

    assert "<script>" not in text
    assert "alert(" not in text
    assert "onload" not in text
    assert "onclick" not in text
    assert "<!DOCTYPE" not in text
    assert "ENTITY" not in text


def test_file_size_limit_35mb():
    # Verify that exceeding 35 MB raises ImageValidationError
    oversized = b"0" * (settings.MAX_FILE_BYTES + 1024)
    try:
        validate_image_data(oversized, "huge.jpg")
        assert False, "Should have raised ImageValidationError"
    except ImageValidationError as e:
        assert "35 MB" in str(e)


def test_rule_5_size_retention():
    # If optimization would make file larger, retain original
    small_data = create_sample_jpeg((20, 20))
    res = optimize_single_image(small_data, "tiny.jpg", mode="visual")
    assert res["optimized_size"] <= res["original_size"]
    assert res["bytes_saved"] >= 0


def test_lossless_pixel_integrity():
    png_bytes = create_sample_png(has_alpha=True)
    res = optimize_single_image(png_bytes, "graphic.png", mode="lossless")
    
    with Image.open(io.BytesIO(png_bytes)) as orig, Image.open(io.BytesIO(res["data"])) as opt:
        assert orig.size == opt.size
        assert verify_pixel_integrity(orig, opt) is True


def test_conversion_preserves_alpha():
    alpha_png = create_sample_png(has_alpha=True)
    try:
        # Converting RGBA to JPEG without explicit authorization must fail
        convert_image(alpha_png, "PNG", "JPEG", allow_discard_alpha=False)
        assert False, "Should have raised ConversionError"
    except ConversionError as e:
        assert "transparent image to JPEG" in str(e)


def test_smart_format_recommendation():
    rec_fmt, reason = recommend_best_format("PNG", has_alpha=True, is_animated=False, is_multi_page=False, width=800, height=600)
    assert rec_fmt == "WEBP"
    assert "alpha transparency" in reason


def test_security_auth_primitives():
    pw = "SuperSecurePassword2026!"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

    token = create_access_token({"sub": "user-123", "plan": "pro"}, expires_delta_seconds=3600)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["plan"] == "pro"


def test_zip_service_no_duplicate_names():
    files = [
        ("image.png", b"content1"),
        ("image.png", b"content2"),
        ("image.png", b"content3"),
    ]
    zip_bytes = create_zip_archive(files)
    assert len(zip_bytes) > 0
    import zipfile
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert len(names) == 3
        assert len(set(names)) == 3  # All unique!

