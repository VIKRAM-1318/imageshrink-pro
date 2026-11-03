"""
TIFF Optimization Module.
Handles LZW, Deflate, and Adobe Deflate compression, preserving multi-page archives.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Tuple
from PIL import Image, ImageSequence


def optimize_tiff(
    data: bytes,
    mode: str = "visual",
    quality: int = 90,
    keep_metadata: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Optimize TIFF with Deflate or LZW lossless compression, preserving all pages.
    """
    with Image.open(BytesIO(data)) as img:
        n_pages = getattr(img, "n_frames", 1)
        pages: List[Image.Image] = []
        for frame in ImageSequence.Iterator(img):
            pages.append(frame.copy())

        out = BytesIO()
        # Use deflate compression for highest space saving in TIFF
        pages[0].save(
            out,
            format="TIFF",
            save_all=True if len(pages) > 1 else False,
            append_images=pages[1:] if len(pages) > 1 else [],
            compression="tiff_deflate",
        )
        candidate = out.getvalue()
        if len(candidate) >= len(data):
            return data, {"format": "TIFF", "retained_original": True}

        return candidate, {
            "format": "TIFF",
            "pages": len(pages),
            "compression": "deflate",
            "width": img.width,
            "height": img.height,
        }

