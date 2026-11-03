"""
WebP Optimization Module.
Supports lossy, lossless, alpha channel preservation, and multi-frame animated WebP.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Tuple
from PIL import Image, ImageSequence


def optimize_webp(
    data: bytes,
    mode: str = "visual",
    quality: int = 85,
    keep_metadata: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Optimize WebP image:
    - Lossless mode: lossless=True, effort=6
    - Visual mode: lossy quality=85, effort=6
    - Custom mode: user quality 1-100
    - Full animation preservation when animated WebP is detected.
    """
    with Image.open(BytesIO(data)) as img:
        is_animated = getattr(img, "is_animated", False) and img.n_frames > 1
        out = BytesIO()

        if is_animated:
            # Preserve all frames, timings, and loop configuration
            frames: List[Image.Image] = []
            durations: List[int] = []
            for frame in ImageSequence.Iterator(img):
                frames.append(frame.copy())
                durations.append(frame.info.get("duration", 100))

            loop = img.info.get("loop", 0)
            lossless_flag = (mode == "lossless")
            q = 100 if mode == "lossless" else (85 if mode == "visual" else quality)

            frames[0].save(
                out,
                format="WEBP",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=loop,
                lossless=lossless_flag,
                quality=q,
                method=6,
            )
        else:
            if mode == "lossless":
                img.save(out, format="WEBP", lossless=True, quality=100, method=6)
            elif mode == "visual":
                img.save(out, format="WEBP", lossless=False, quality=85, method=6)
            else:  # custom
                img.save(out, format="WEBP", lossless=False, quality=max(1, min(100, quality)), method=6)

        candidate = out.getvalue()
        if len(candidate) >= len(data):
            return data, {"format": "WEBP", "retained_original": True}

        return candidate, {
            "format": "WEBP",
            "animated": is_animated,
            "width": img.width,
            "height": img.height,
        }

