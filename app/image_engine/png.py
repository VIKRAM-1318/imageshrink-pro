"""
PNG Optimization Module.
Handles genuine lossless compression, palette reduction (<= 256 colors),
transparency preservation, and pixel-data integrity verification.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Tuple
from PIL import Image, ImageChops


def verify_pixel_integrity(img1: Image.Image, img2: Image.Image) -> bool:
    """Verifies that every decoded pixel in both images is bit-for-bit identical."""
    if img1.size != img2.size:
        return False
    c1 = img1.convert("RGBA")
    c2 = img2.convert("RGBA")
    diff = ImageChops.difference(c1, c2)
    return not diff.getbbox()  # Empty bounding box means zero difference


def optimize_png(
    data: bytes,
    mode: str = "lossless",
    quality: int = 90,
    keep_metadata: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Optimize PNG image.
    - Lossless mode: Deflate compression level 9, optimize=True, verify pixel integrity.
    - Visual mode: Adaptive palette quantization if visually indistinguishable, or high-compression RGBA.
    - Custom mode: User-specified palette size or lossy PNG quantization.
    """
    with Image.open(BytesIO(data)) as img:
        has_alpha = "A" in img.getbands() or img.mode in ("RGBA", "LA", "P")
        original_mode = img.mode
        out = BytesIO()

        if mode == "lossless":
            # True lossless recompression
            target_img = img
            target_img.save(out, format="PNG", optimize=True, compress_level=9)
            candidate = out.getvalue()

            # Verify pixel equality
            with Image.open(BytesIO(candidate)) as verified_img:
                if not verify_pixel_integrity(img, verified_img):
                    # Fallback to original if any mismatch occurred
                    return data, {"format": "PNG", "verified_lossless": True, "retained_original": True}

            if len(candidate) >= len(data):
                return data, {"format": "PNG", "verified_lossless": True, "retained_original": True}

            return candidate, {
                "format": "PNG",
                "verified_lossless": True,
                "width": img.width,
                "height": img.height,
            }

        elif mode == "visual":
            # Visually lossless: check if image can use adaptive palette (P mode with RGBA alpha)
            if img.mode not in ("RGB", "RGBA"):
                work_img = img.convert("RGBA" if has_alpha else "RGB")
            else:
                work_img = img

            # If image has <= 256 colors naturally, convert to palette without any loss
            num_colors = len(work_img.getcolors(maxcolors=256) or [])
            if 0 < num_colors <= 256:
                palette_img = work_img.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
                palette_img.save(out, format="PNG", optimize=True, compress_level=9)
            else:
                work_img.save(out, format="PNG", optimize=True, compress_level=9)

            candidate = out.getvalue()
            if len(candidate) >= len(data):
                return data, {"format": "PNG", "retained_original": True}

            return candidate, {"format": "PNG", "width": img.width, "height": img.height}

        else:  # custom
            work_img = img.convert("RGBA" if has_alpha else "RGB")
            if quality < 80:
                # Quantize palette for substantial compression
                colors = max(16, min(256, int(256 * (quality / 100.0))))
                quantized = work_img.quantize(colors=colors, dither=Image.Dither.FLOYDSTEINBERG)
                quantized.save(out, format="PNG", optimize=True, compress_level=9)
            else:
                work_img.save(out, format="PNG", optimize=True, compress_level=9)

            candidate = out.getvalue()
            if len(candidate) >= len(data):
                return data, {"format": "PNG", "retained_original": True}

            return candidate, {"format": "PNG", "quality": quality, "width": img.width, "height": img.height}

