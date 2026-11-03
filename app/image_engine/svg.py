"""
SVG Optimization Module.
Performs XML minification, stripping metadata, comments, editor tags, and redundant whitespace.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple
from app.image_engine.validator import sanitize_svg_data


def optimize_svg(
    data: bytes,
    mode: str = "visual",
    quality: int = 90,
    keep_metadata: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Minify and sanitize SVG.
    """
    sanitized = sanitize_svg_data(data)
    text = sanitized.decode("utf-8", errors="replace")

    # Strip XML comments: <!-- ... -->
    text = re.sub(r"<!--[\s\S]*?-->", "", text)

    # Strip editor namespaces and metadata
    if not keep_metadata:
        text = re.sub(r"<metadata[\s\S]*?</metadata>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+xmlns:inkscape=\"[^\"]*\"", "", text)
        text = re.sub(r"\s+xmlns:sodipodi=\"[^\"]*\"", "", text)
        text = re.sub(r"\s+inkscape:[a-zA-Z0-9_\-]+=\"[^\"]*\"", "", text)
        text = re.sub(r"\s+sodipodi:[a-zA-Z0-9_\-]+=\"[^\"]*\"", "", text)

    # Collapse multiple whitespaces and strip trailing spaces around tags
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r">\s+<", "><", text)
    candidate = text.strip().encode("utf-8")

    if len(candidate) >= len(data):
        return data, {"format": "SVG", "retained_original": True}

    return candidate, {"format": "SVG", "minified": True}

