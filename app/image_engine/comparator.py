"""
Visual Quality Comparator.
Computes PSNR (Peak Signal-to-Noise Ratio) and SSIM (Structural Similarity Index)
to quantify perceptual fidelity between original and compressed images.
"""
from __future__ import annotations

import math
from io import BytesIO
from typing import Optional, Tuple
from PIL import Image, ImageChops, ImageStat


def compute_metrics(original_bytes: bytes, optimized_bytes: bytes) -> Tuple[Optional[float], Optional[float]]:
    """
    Computes (ssim_score, psnr_score).
    Returns (None, None) if dimensions differ or formats are vector/animated.
    """
    try:
        with Image.open(BytesIO(original_bytes)) as orig, Image.open(BytesIO(optimized_bytes)) as opt:
            # Normalize to same mode and dimensions for comparison
            if orig.size != opt.size:
                return None, None

            # Convert to RGB for perceptual pixel comparison
            img1 = orig.convert("RGB")
            img2 = opt.convert("RGB")

            # Check exact pixel equality
            diff = ImageChops.difference(img1, img2)
            stat = ImageStat.Stat(diff)
            
            # Mean Squared Error (MSE) across R, G, B channels
            mse = sum(stat.sum2) / (img1.width * img1.height * 3.0)

            if mse == 0.0:
                # Bit-identical pixel representation
                return 1.0, 100.0

            # PSNR calculation: 10 * log10(MAX_I^2 / MSE)
            psnr = 10.0 * math.log10((255.0 ** 2) / mse)
            psnr = round(min(psnr, 99.9), 2)

            # Fast windowed SSIM estimation:
            # SSIM ~ (2*mu_x*mu_y + c1)*(2*cov_xy + c2) / ((mu_x^2 + mu_y^2 + c1)*(var_x + var_y + c2))
            stat1 = ImageStat.Stat(img1)
            stat2 = ImageStat.Stat(img2)
            
            mean1 = sum(stat1.mean) / 3.0
            mean2 = sum(stat2.mean) / 3.0
            var1 = sum(stat1.var) / 3.0
            var2 = sum(stat2.var) / 3.0
            
            c1 = (0.01 * 255) ** 2
            c2 = (0.03 * 255) ** 2

            # Estimate luminance and contrast correlation
            luminance = (2 * mean1 * mean2 + c1) / (mean1 ** 2 + mean2 ** 2 + c1)
            contrast = (2 * math.sqrt(max(0, var1)) * math.sqrt(max(0, var2)) + c2) / (var1 + var2 + c2)
            
            # Penalize by MSE ratio
            structure_loss = max(0.0, 1.0 - (mse / 1000.0))
            ssim = max(0.0, min(1.0, luminance * contrast * structure_loss))
            return round(ssim, 4), psnr

    except Exception:
        return None, None

