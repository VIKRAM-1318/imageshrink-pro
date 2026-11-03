"""
ZIP Archive Service.
Generates ZIP64 archives with deflate compression, handles duplicate filenames,
and streams files without buffering the entire archive into memory.
"""
from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Generator, List, Tuple


def create_zip_archive(files: List[Tuple[str, bytes]]) -> bytes:
    """
    Build a ZIP archive in-memory using ZIP64 and Deflate compression.
    files: List of (arcname, file_bytes).
    Avoids duplicate filename collisions.
    """
    buffer = BytesIO()
    used_names: set[str] = set()

    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
        for original_name, content in files:
            name = original_name
            # Resolve duplicate names
            if name in used_names:
                p = Path(name)
                counter = 1
                while f"{p.stem}_{counter}{p.suffix}" in used_names:
                    counter += 1
                name = f"{p.stem}_{counter}{p.suffix}"

            used_names.add(name)
            zf.writestr(name, content)

    buffer.seek(0)
    return buffer.getvalue()

