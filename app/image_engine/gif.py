"""
GIF Optimization Module.
Handles animated and static GIFs, preserving frame timing, loop counts,
transparency indices, and optimizing palette quantization.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Tuple
from PIL import Image, ImageSequence


def optimize_gif(
    data: bytes,
    mode: str = "visual",
    quality: int = 90,
    keep_metadata: bool = False,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Optimize GIF image while strictly preserving animation, frame timing, and transparency.
    """
    with Image.open(BytesIO(data)) as img:
        is_animated = getattr(img, "is_animated", False) and img.n_frames > 1
        out = BytesIO()

        if is_animated:
            frames: List[Image.Image] = []
            durations: List[int] = []
            disposals: List[int] = []

            for frame in ImageSequence.Iterator(img):
                durations.append(frame.info.get("duration", 100))
                disposals.append(frame.info.get("disposal", 2))
                # Convert frame preserving transparency
                frame_conv = frame.convert("RGBA")
                if mode == "visual" or (mode == "custom" and quality < 90):
                    colors = 128 if quality < 70 else 256
                    frame_conv = frame_conv.quantize(colors=colors, dither=Image.Dither.FLOYDSTEINBERG)
                frames.append(frame_conv)

            loop = img.info.get("loop", 0)
            frames[0].save(
                out,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=loop,
                disposal=disposals,
                optimize=True,
            )
        else:
            img_conv = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            if mode == "visual" or (mode == "custom" and quality < 90):
                colors = 128 if quality < 70 else 256
                img_conv = img_conv.quantize(colors=colors, dither=Image.Dither.FLOYDSTEINBERG)
            img_conv.save(out, format="GIF", optimize=True)

        candidate = out.getvalue()
        if len(candidate) >= len(data):
            return data, {"format": "GIF", "retained_original": True}

        return candidate, {
            "format": "GIF",
            "animated": is_animated,
            "width": img.width,
            "height": img.height,
        }

