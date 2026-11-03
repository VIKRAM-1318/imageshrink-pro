"""
Image Validator and Security Filter.
Enforces 35 MB maximum file sizes, detects decompression bombs, validates magic bytes,
and sanitizes SVGs against malicious scripts and XML external entities.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Tuple

from PIL import Image

from app.config import settings
from app.image_engine.detector import detect_format_from_bytes

# Set Pillow decompression bomb limits
Image.MAX_IMAGE_PIXELS = settings.MAX_PIXEL_COUNT


class ImageValidationError(ValueError):
    """Raised when an uploaded image fails validation or security policies."""
    pass


def validate_image_data(data: bytes, filename: str) -> Tuple[str, str, int]:
    """
    Validates uploaded raw bytes:
    1. Size check <= 35 MB.
    2. Format detection via magic bytes.
    3. Decompression bomb check for raster formats.
    4. SVG security check.
    Returns (detected_format, canonical_ext, size_bytes).
    """
    size = len(data)
    if size == 0:
        raise ImageValidationError("File is empty (0 bytes).")

    if size > settings.MAX_FILE_BYTES:
        max_mb = settings.MAX_FILE_BYTES // (1024 * 1024)
        raise ImageValidationError(f"File size exceeds maximum allowed limit of {max_mb} MB.")

    detected_format, ext = detect_format_from_bytes(data)

    if detected_format == "UNKNOWN":
        # Check if user uploaded valid image format that needs relaxed detection
        raise ImageValidationError("Unsupported or corrupted image file signature.")

    # SVG-specific security validation
    if detected_format == "SVG":
        sanitize_svg_data(data)
        return detected_format, ext, size

    # Raster formats: inspect header with Pillow to verify sanity
    try:
        with Image.open(BytesIO(data)) as img:
            width, height = img.size
            if width * height > settings.MAX_PIXEL_COUNT:
                raise ImageValidationError(
                    f"Image dimensions ({width}x{height}) exceed maximum pixel limit (Decompression Bomb protection)."
                )
    except ImageValidationError:
        raise
    except Exception as exc:
        raise ImageValidationError(f"Corrupted or invalid image structure: {exc}")

    return detected_format, ext, size


def sanitize_svg_data(data: bytes) -> bytes:
    """
    Sanitize SVG markup:
    - Remove script tags
    - Remove inline event handlers (onclick, onload, onerror, etc.)
    - Remove external entity references / DTD declarations (prevent XXE)
    - Remove dangerous foreignObject tags
    """
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        raise ImageValidationError("Invalid UTF-8 encoding in SVG file.")

    # Remove XML DTD entities and DOCTYPE blocks including internal subsets
    text = re.sub(r"<!DOCTYPE[\s\S]*?(?:\[[\s\S]*?\]\s*)?>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<!ENTITY[\s\S]*?>", "", text, flags=re.IGNORECASE)

    # Remove <script ... </script>
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)

    # Remove <foreignObject ... </foreignObject>
    text = re.sub(r"<foreignObject[\s\S]*?</foreignObject>", "", text, flags=re.IGNORECASE)

    # Remove event handlers like onload, onerror, onclick, onmouseover
    text = re.sub(r'\s+on\w+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', "", text, flags=re.IGNORECASE)

    # Remove javascript: URIs
    text = re.sub(r"(href|xlink:href)\s*=\s*[\"']javascript:[^\"']*[\"']", "", text, flags=re.IGNORECASE)

    # Validate resulting XML parses properly
    try:
        ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as pe:
        raise ImageValidationError(f"Malformed SVG XML structure: {pe}")

    return text.encode("utf-8")

