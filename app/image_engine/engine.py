"""
Central Optimization Engine.
Orchestrates format-specific pipelines, lossless verification, visual-lossless compression,
custom configurations, format conversions, and quality metrics.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from PIL import Image

from app.image_engine.comparator import compute_metrics
from app.image_engine.converter import convert_image, recommend_best_format
from app.image_engine.gif import optimize_gif
from app.image_engine.jpeg import optimize_jpeg
from app.image_engine.other_formats import optimize_avif, optimize_bmp, optimize_heic, optimize_ico
from app.image_engine.png import optimize_png
from app.image_engine.svg import optimize_svg
from app.image_engine.tiff import optimize_tiff
from app.image_engine.validator import validate_image_data
from app.image_engine.webp import optimize_webp


def optimize_single_image(
    data: bytes,
    original_filename: str,
    mode: str = "visual",  # "lossless", "visual", "custom"
    target_format: Optional[str] = None,  # "original", "JPEG", "PNG", "WEBP", "auto"
    quality: int = 85,
    keep_metadata: bool = False,
    resize_max_width: Optional[int] = None,
    resize_max_height: Optional[int] = None,
    allow_discard_alpha: bool = False,
    target_size_kb: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Main entry point for optimizing a single image.
    Validates input, processes through format pipeline or conversion,
    and returns comprehensive metrics.
    """
    detected_format, canonical_ext, original_size = validate_image_data(data, original_filename)

    # Inspect dimensions and transparency
    orig_width, orig_height = 0, 0
    has_alpha = False
    is_animated = False
    is_multi_page = False

    if detected_format != "SVG":
        try:
            with Image.open(BytesIO(data)) as img:
                orig_width, orig_height = img.size
                has_alpha = "A" in img.getbands() or img.mode in ("RGBA", "LA", "P")
                is_animated = getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1
                is_multi_page = getattr(img, "n_frames", 1) > 1 and detected_format == "TIFF"
        except Exception:
            pass

    # Optional Resize (custom mode)
    working_data = data
    if (
        (resize_max_width or resize_max_height)
        and orig_width > 0
        and orig_height > 0
        and detected_format != "SVG"
    ):
        try:
            with Image.open(BytesIO(working_data)) as img:
                target_w = resize_max_width or orig_width
                target_h = resize_max_height or orig_height
                if orig_width > target_w or orig_height > target_h:
                    img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
                    out = BytesIO()
                    save_fmt = "PNG" if has_alpha else ("JPEG" if detected_format == "JPEG" else img.format or "PNG")
                    img.save(out, format=save_fmt)
                    working_data = out.getvalue()
                    orig_width, orig_height = img.size
        except Exception:
            working_data = data

    # Intelligent format recommendation if requested
    rec_format, rec_reason = recommend_best_format(
        detected_format, has_alpha, is_animated, is_multi_page, orig_width, orig_height
    )

    actual_target = target_format
    if actual_target == "auto":
        actual_target = rec_format

    # Handle format conversion if required
    if actual_target and actual_target.upper() not in ("ORIGINAL", "KEEP", detected_format):
        opt_bytes, final_format, meta = convert_image(
            working_data,
            source_format=detected_format,
            target_format=actual_target,
            mode=mode,
            quality=quality,
            allow_discard_alpha=allow_discard_alpha,
        )
    else:
        # Format-specific optimization
        final_format = detected_format
        if detected_format == "JPEG":
            opt_bytes, meta = optimize_jpeg(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        elif detected_format == "PNG":
            opt_bytes, meta = optimize_png(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        elif detected_format == "WEBP":
            opt_bytes, meta = optimize_webp(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        elif detected_format == "GIF":
            opt_bytes, meta = optimize_gif(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        elif detected_format == "TIFF":
            opt_bytes, meta = optimize_tiff(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        elif detected_format == "SVG":
            opt_bytes, meta = optimize_svg(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        elif detected_format == "ICO":
            opt_bytes, meta = optimize_ico(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        elif detected_format == "BMP":
            opt_bytes, meta = optimize_bmp(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        elif detected_format == "AVIF":
            opt_bytes, meta = optimize_avif(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        elif detected_format == "HEIC":
            opt_bytes, meta = optimize_heic(working_data, mode=mode, quality=quality, keep_metadata=keep_metadata)
        else:
            opt_bytes, meta = working_data, {"retained_original": True}

    # Target file size constraint enforcement (Business & Premium plans)
    if target_size_kb and target_size_kb > 0 and len(opt_bytes) > (target_size_kb * 1024) and detected_format != "SVG":
        target_bytes = target_size_kb * 1024
        low_q, high_q = 10, quality
        best_candidate = opt_bytes
        for _ in range(5):
            if low_q > high_q:
                break
            mid_q = (low_q + high_q) // 2
            cand_bytes = opt_bytes
            if final_format == "JPEG":
                cand_bytes, _ = optimize_jpeg(working_data, mode="custom", quality=mid_q, keep_metadata=keep_metadata)
            elif final_format == "WEBP":
                cand_bytes, _ = optimize_webp(working_data, mode="custom", quality=mid_q, keep_metadata=keep_metadata)
            elif final_format == "AVIF":
                cand_bytes, _ = optimize_avif(working_data, mode="custom", quality=mid_q, keep_metadata=keep_metadata)
            
            if len(cand_bytes) <= target_bytes:
                best_candidate = cand_bytes
                low_q = mid_q + 1
            else:
                high_q = mid_q - 1
                best_candidate = cand_bytes
        opt_bytes = best_candidate

    # Strict Rule 5: When candidate output is larger than original, retain smaller original.
    retained_original = False
    if len(opt_bytes) >= original_size and (not actual_target or actual_target.upper() in ("ORIGINAL", "KEEP", detected_format)):
        opt_bytes = data
        final_format = detected_format
        retained_original = True

    optimized_size = len(opt_bytes)
    bytes_saved = max(0, original_size - optimized_size)
    percentage_saved = round((bytes_saved / original_size) * 100, 2) if original_size > 0 else 0.0

    # Compute SSIM and PSNR
    ssim, psnr = None, None
    if detected_format not in ("SVG", "GIF") and not is_animated:
        ssim, psnr = compute_metrics(data, opt_bytes)

    # Determine extension
    ext_map = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "GIF": ".gif",
        "TIFF": ".tiff",
        "SVG": ".svg",
        "ICO": ".ico",
        "BMP": ".bmp",
        "AVIF": ".avif",
        "HEIC": ".heic",
    }
    out_ext = ext_map.get(final_format, canonical_ext)
    stem = Path(original_filename).stem
    output_filename = f"{stem}_optimized{out_ext}"

    # Get final dimensions
    opt_width, opt_height = orig_width, orig_height
    if detected_format != "SVG":
        try:
            with Image.open(BytesIO(opt_bytes)) as final_img:
                opt_width, opt_height = final_img.size
        except Exception:
            pass

    return {
        "data": opt_bytes,
        "output_filename": output_filename,
        "original_format": detected_format,
        "output_format": final_format,
        "original_size": original_size,
        "optimized_size": optimized_size,
        "bytes_saved": bytes_saved,
        "percentage_saved": percentage_saved,
        "original_width": orig_width,
        "original_height": orig_height,
        "optimized_width": opt_width,
        "optimized_height": opt_height,
        "ssim": ssim,
        "psnr": psnr,
        "retained_original": retained_original,
        "recommendation": {
            "format": rec_format,
            "explanation": rec_reason,
        },
    }

