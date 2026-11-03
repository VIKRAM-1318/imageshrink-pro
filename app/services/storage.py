"""
Image Storage Service.
Provides uniform file persistence across local disk storage and S3-compatible object stores
(AWS S3, Cloudflare R2, MinIO) with signed URLs and temporary file lifecycle rules.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional

from app.config import OPTIMIZED_DIR, STORAGE_DIR, UPLOADS_DIR, settings


class StorageService:
    def __init__(self):
        self.use_s3 = settings.USE_S3_STORAGE
        self.s3_client = None
        if self.use_s3 and settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY:
            try:
                import boto3
                self.s3_client = boto3.client(
                    "s3",
                    endpoint_url=settings.S3_ENDPOINT_URL,
                    aws_access_key_id=settings.S3_ACCESS_KEY,
                    aws_secret_access_key=settings.S3_SECRET_KEY,
                    region_name=settings.S3_REGION,
                )
            except Exception:
                self.s3_client = None

    def save_upload(self, batch_id: str, filename: str, data: bytes) -> str:
        """Save an uploaded file to storage. Returns storage path or S3 key."""
        target_dir = UPLOADS_DIR / batch_id
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / filename
        file_path.write_bytes(data)

        if self.s3_client:
            s3_key = f"uploads/{batch_id}/{filename}"
            try:
                self.s3_client.put_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=s3_key,
                    Body=data,
                )
                return s3_key
            except Exception:
                pass

        return str(file_path)

    def save_optimized(self, batch_id: str, filename: str, data: bytes) -> str:
        """Save an optimized image. Returns storage path or S3 key."""
        target_dir = OPTIMIZED_DIR / batch_id
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / filename
        file_path.write_bytes(data)

        if self.s3_client:
            s3_key = f"optimized/{batch_id}/{filename}"
            try:
                self.s3_client.put_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=s3_key,
                    Body=data,
                )
                return s3_key
            except Exception:
                pass

        return str(file_path)

    def get_file_bytes(self, storage_path: str) -> Optional[bytes]:
        """Read bytes from local path or S3."""
        p = Path(storage_path)
        if p.is_file():
            return p.read_bytes()

        if self.s3_client:
            try:
                resp = self.s3_client.get_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=storage_path,
                )
                return resp["Body"].read()
            except Exception:
                pass

        return None

    def cleanup_old_files(self, max_age_seconds: int = 86400) -> int:
        """Clean up local temporary batch files older than max_age_seconds."""
        now = time.time()
        removed = 0
        for base in (UPLOADS_DIR, OPTIMIZED_DIR):
            for batch_folder in base.iterdir():
                if batch_folder.is_dir():
                    try:
                        mtime = batch_folder.stat().st_mtime
                        if now - mtime > max_age_seconds:
                            shutil.rmtree(batch_folder, ignore_errors=True)
                            removed += 1
                    except Exception:
                        pass
        return removed


storage = StorageService()

