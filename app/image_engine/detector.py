"""
Image Format Detector using Magic Bytes.
Detects image format using binary file signatures rather than untrusted file extensions.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple


def detect_format_from_bytes(data: bytes) -> Tuple[str, str]:
    """
    Detect format by checking leading bytes (file signatures / magic bytes).
    Returns (format_name, canonical_extension).
    """
    if len(data) < 4:
        return "UNKNOWN", ".bin"

    # PNG: \x89 P N G \r \n \x1a \n
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG", ".png"

    # JPEG: \xFF \xD8 \xFF
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG", ".jpg"

    # GIF: GIF87a or GIF89a
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "GIF", ".gif"

    # WebP: RIFF .... WEBP
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "WEBP", ".webp"

    # BMP: BM
    if data.startswith(b"BM"):
        return "BMP", ".bmp"

    # TIFF: II*\x00 (little-endian) or MM\x00* (big-endian)
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
        return "TIFF", ".tiff"

    # ICO: \x00\x00\x01\x00
    if data.startswith(b"\x00\x00\x01\x00"):
        return "ICO", ".ico"

    # ISO Base Media File Format (AVIF, HEIC, HEIF)
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return "AVIF", ".avif"
        if brand in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"):
            return "HEIC", ".heic"

    # SVG: Check for XML declaration and <svg tag
    sample = data[:1024].lower()
    if b"<svg" in sample or (b"<?xml" in sample and b"<svg" in data[:4096].lower()):
        return "SVG", ".svg"

    return "UNKNOWN", ".bin"

