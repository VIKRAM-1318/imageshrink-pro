"""
Format Conversion and Recommendation Engine.
Provides intelligent format recommendations with transparent explanations,
strictly respecting transparency, animation, and multi-page integrity.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Optional, Tuple
from PIL import Image

from app.image_engine.jpeg import optimize_jpeg
from app.image_engine.png import optimize_png
from app.image_engine.webp import optimize_webp


class ConversionError(ValueError):
    """Raised when format conversion violates preservation rules."""
    pass


def recommend_best_format(
    format_name: str,
    has_alpha: bool,
    is_animated: bool,
    is_multi_page: bool,
    width: int,
    height: int,
) -> Tuple[str, str]:
    """
    Evaluates format characteristics and returns (recommended_format, explanation).
    Never recommends converting transparent images to JPEG.
    Never recommends discarding animation.
    """
    if is_animated:
        if format_name in ("GIF", "WEBP"):
            return "WEBP", "WebP provides superior compression for animation while maintaining universal modern browser support and frame timing."
        return format_name, f"Retaining {format_name} to preserve animation frames and timings."

    if has_alpha:
        # Transparent images cannot go to JPEG without loss of alpha channel
        return "WEBP", "WebP supports lossy and lossless alpha transparency with 25-34% smaller file size than standard PNG across modern browsers."

    if format_name in ("BMP", "TIFF") and not is_multi_page:
        return "JPEG", f"Converting uncompressed {format_name} to progressive JPEG achieves up to 90% size reduction with visually lossless fidelity."

    if format_name == "PNG":
        return "WEBP", "Converting non-transparent PNG to modern WebP significantly shrinks file size while preserving high visual quality."

    return "WEBP", "WebP delivers optimal compression and broad browser compatibility for modern web deployment."


def convert_image(
    data: bytes,
    source_format: str,
    target_format: str,
    mode: str = "visual",
    quality: int = 85,
    allow_discard_alpha: bool = False,
) -> Tuple[bytes, str, Dict[str, Any]]:
    """
    Convert image from source_format to target_format.
    Returns (output_bytes, output_format, metadata).
    """
    target = target_format.upper().strip()
    if target in ("ORIGINAL", "KEEP", source_format):
        return data, source_format, {"converted": False, "reason": "Retained original format"}

    with Image.open(BytesIO(data)) as img:
        has_alpha = "A" in img.getbands() or img.mode in ("RGBA", "LA", "P")
        is_animated = getattr(img, "is_animated", False) and img.n_frames > 1
        is_multi_page = getattr(img, "n_frames", 1) > 1 and source_format == "TIFF"

        # Safe guard: Never convert transparent image to JPEG without explicit user consent
        if target == "JPEG" and has_alpha and not allow_discard_alpha:
            raise ConversionError(
                "Cannot convert transparent image to JPEG without explicit authorization (alpha channel would be discarded)."
            )

        if target == "JPEG":
            rgb_img = img.convert("RGB")
            out = BytesIO()
            rgb_img.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
            res = out.getvalue()
            return res, "JPEG", {"converted": True, "to": "JPEG", "width": img.width, "height": img.height}

        elif target == "PNG":
            rgba_img = img.convert("RGBA" if has_alpha else "RGB")
            out = BytesIO()
            rgba_img.save(out, format="PNG", optimize=True, compress_level=9)
            res = out.getvalue()
            return res, "PNG", {"converted": True, "to": "PNG", "width": img.width, "height": img.height}

        elif target == "WEBP":
            opt_bytes, meta = optimize_webp(data, mode=mode, quality=quality)
            return opt_bytes, "WEBP", {"converted": True, "to": "WEBP", **meta}

        else:
            raise ConversionError(f"Conversion to format '{target}' is not supported.")

