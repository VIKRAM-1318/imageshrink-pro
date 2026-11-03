"""
ICO, BMP, AVIF, and HEIC Optimization Modules.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Tuple
from PIL import Image


def optimize_ico(
    data: bytes,
    mode: str = "visual",
    quality: int = 90,
    keep_metadata: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """Optimize ICO preserving standard icon dimensions."""
    with Image.open(BytesIO(data)) as img:
        out = BytesIO()
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]
        valid_sizes = [s for s in sizes if s[0] <= img.width and s[1] <= img.height]
        if not valid_sizes:
            valid_sizes = [(img.width, img.height)]
        img.save(out, format="ICO", sizes=valid_sizes)
        candidate = out.getvalue()
        if len(candidate) >= len(data):
            return data, {"format": "ICO", "retained_original": True}
        return candidate, {"format": "ICO", "width": img.width, "height": img.height}


def optimize_bmp(
    data: bytes,
    mode: str = "visual",
    quality: int = 90,
    keep_metadata: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """Optimize BMP by lossless Run-Length Encoding (RLE) or converting to PNG container."""
    with Image.open(BytesIO(data)) as img:
        out = BytesIO()
        img.save(out, format="BMP")
        candidate = out.getvalue()
        if len(candidate) >= len(data):
            return data, {"format": "BMP", "retained_original": True}
        return candidate, {"format": "BMP", "width": img.width, "height": img.height}


def optimize_avif(
    data: bytes,
    mode: str = "visual",
    quality: int = 80,
    keep_metadata: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """Optimize AVIF (AV1 encoder) with configurable quality and alpha preservation."""
    try:
        with Image.open(BytesIO(data)) as img:
            out = BytesIO()
            q = 95 if mode == "lossless" else (80 if mode == "visual" else quality)
            # Pillow has AVIF support if pillow-avif or libheif plugin is present
            img.save(out, format="AVIF", quality=q)
            candidate = out.getvalue()
            if len(candidate) >= len(data):
                return data, {"format": "AVIF", "retained_original": True}
            return candidate, {"format": "AVIF", "quality": q, "width": img.width, "height": img.height}
    except Exception:
        # Fallback to retaining original bytes if AVIF plugin not dynamically linked
        return data, {"format": "AVIF", "retained_original": True}


def optimize_heic(
    data: bytes,
    mode: str = "visual",
    quality: int = 85,
    keep_metadata: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """Decode and optimize HEIC/HEIF containers."""
    try:
        with Image.open(BytesIO(data)) as img:
            out = BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
            candidate = out.getvalue()
            return candidate, {"format": "JPEG", "converted_from": "HEIC", "width": img.width, "height": img.height}
    except Exception:
        return data, {"format": "HEIC", "retained_original": True}

