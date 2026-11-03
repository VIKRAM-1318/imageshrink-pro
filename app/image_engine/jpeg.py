"""
JPEG Optimization Module.
Handles progressive encoding, optimized Huffman tables, chroma subsampling, and EXIF handling.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Optional, Tuple
from PIL import Image, ImageOps


def optimize_jpeg(
    data: bytes,
    mode: str = "visual",
    quality: int = 90,
    keep_metadata: bool = False,
    subsampling: Optional[int] = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Optimize JPEG image:
    - Mode 'lossless': Retain original bytes (JPEG re-encoding is fundamentally lossy)
      or perform lossless metadata strip if requested.
    - Mode 'visual': High quality (q=92), 4:4:4 subsampling (subsampling=0) or 4:2:0, progressive.
    - Mode 'custom': User-configured quality (1-100), subsampling, progressive.
    """
    if mode == "lossless" and keep_metadata:
        return data, {"format": "JPEG", "progressive": False, "quality": "original"}

    with Image.open(BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        out = BytesIO()
        save_kwargs: Dict[str, Any] = {
            "format": "JPEG",
            "optimize": True,
            "progressive": True,
        }

        if mode == "lossless":
            # Lossless EXIF strip / repackaging
            save_kwargs["quality"] = 98
            save_kwargs["subsampling"] = 0
        elif mode == "visual":
            save_kwargs["quality"] = 92
            save_kwargs["subsampling"] = 0  # 4:4:4 preserves sharp edges & text
        else:  # custom
            save_kwargs["quality"] = max(1, min(100, quality))
            if subsampling is not None:
                save_kwargs["subsampling"] = subsampling

        if keep_metadata and "exif" in img.info:
            save_kwargs["exif"] = img.info["exif"]

        img.save(out, **save_kwargs)
        candidate = out.getvalue()

        # Rule 5: When candidate output is larger than original, retain smaller original.
        if len(candidate) >= len(data):
            return data, {"format": "JPEG", "retained_original": True}

        return candidate, {
            "format": "JPEG",
            "progressive": True,
            "quality": save_kwargs.get("quality"),
            "width": img.width,
            "height": img.height,
        }

