"""
Background Job Processing Service.
Manages asynchronous batch processing, per-file error isolation, progress tracking,
and database record synchronization.
"""
from __future__ import annotations

import concurrent.futures
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from app.database import db_session
from app.image_engine.engine import optimize_single_image
from app.services.storage import storage

# ThreadPoolExecutor for background image optimization
executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)


class JobService:
    @staticmethod
    def create_batch(
        user_id: Optional[str],
        name: str,
        total_files: int,
        mode: str,
        settings_dict: Dict[str, Any],
    ) -> str:
        batch_id = str(uuid.uuid4())
        now = time.time()
        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO upload_batches 
                (id, user_id, name, total_files, processed_files, failed_files, status, mode, settings_json, created_at)
                VALUES (?, ?, ?, ?, 0, 0, 'processing', ?, ?, ?)
                """,
                (batch_id, user_id, name, total_files, mode, json.dumps(settings_dict), now),
            )
        return batch_id

    @staticmethod
    def process_image_task(
        batch_id: str,
        image_id: str,
        filename: str,
        raw_bytes: bytes,
        mode: str,
        target_format: Optional[str],
        quality: int,
        keep_metadata: bool = False,
        resize_max_width: Optional[int] = None,
        resize_max_height: Optional[int] = None,
        target_size_kb: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Processes a single image and writes records atomically."""
        try:
            res = optimize_single_image(
                data=raw_bytes,
                original_filename=filename,
                mode=mode,
                target_format=target_format,
                quality=quality,
                keep_metadata=keep_metadata,
                resize_max_width=resize_max_width,
                resize_max_height=resize_max_height,
                target_size_kb=target_size_kb,
            )

            # Persist optimized file
            opt_path = storage.save_optimized(batch_id, res["output_filename"], res["data"])
            now = time.time()

            with db_session() as conn:
                # Update uploaded_images status
                conn.execute(
                    """
                    UPDATE uploaded_images
                    SET status = 'completed', original_width = ?, original_height = ?
                    WHERE id = ?
                    """,
                    (res["original_width"], res["original_height"], image_id),
                )
                # Insert optimization_results
                res_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO optimization_results
                    (id, image_id, batch_id, output_filename, output_format, output_size, output_width, output_height,
                     bytes_saved, percentage_saved, ssim_score, psnr_score, storage_path, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        res_id,
                        image_id,
                        batch_id,
                        res["output_filename"],
                        res["output_format"],
                        res["optimized_size"],
                        res["optimized_width"],
                        res["optimized_height"],
                        res["bytes_saved"],
                        res["percentage_saved"],
                        res["ssim"],
                        res["psnr"],
                        opt_path,
                        now,
                    ),
                )
                # Increment batch progress
                conn.execute(
                    """
                    UPDATE upload_batches
                    SET processed_files = processed_files + 1,
                        total_original_size = total_original_size + ?,
                        total_optimized_size = total_optimized_size + ?
                    WHERE id = ?
                    """,
                    (res["original_size"], res["optimized_size"], batch_id),
                )

            return {"success": True, "image_id": image_id, "result": res}

        except Exception as exc:
            # Per-file error isolation: a single failed image does NOT halt the batch!
            with db_session() as conn:
                conn.execute(
                    """
                    UPDATE uploaded_images
                    SET status = 'failed', error_message = ?
                    WHERE id = ?
                    """,
                    (str(exc), image_id),
                )
                conn.execute(
                    """
                    UPDATE upload_batches
                    SET failed_files = failed_files + 1
                    WHERE id = ?
                    """,
                    (batch_id,),
                )
            return {"success": False, "image_id": image_id, "error": str(exc)}

    @staticmethod
    def finalize_batch(batch_id: str) -> None:
        """Mark batch as completed and atomically deduct quota for successful images."""
        now = time.time()
        user_id = None
        processed_files = 0
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, processed_files FROM upload_batches WHERE id = ?", (batch_id,))
            row = cur.fetchone()
            if row:
                user_id = row["user_id"]
                processed_files = row["processed_files"]

            conn.execute(
                """
                UPDATE upload_batches
                SET status = 'completed', completed_at = ?
                WHERE id = jobs_id
                """.replace("jobs_id", "?"),
                (now, batch_id),
            )

        # Deduct quota strictly for successful operations and record history
        if user_id and processed_files > 0:
            try:
                from app.services.subscription_service import subscription_service
                results = jobs_service.get_batch_results(batch_id)
                subscription_service.deduct_quota_atomic(user_id, processed_files, batch_id, results)
            except Exception as e:
                logger.error(f"Failed to record quota deduction for batch {batch_id}: {e}")

    @classmethod
    def submit_batch_processing(
        cls,
        batch_id: str,
        files_data: List[Tuple[str, str, bytes]],  # (image_id, filename, bytes)
        mode: str,
        target_format: Optional[str],
        quality: int,
        keep_metadata: bool = False,
        resize_max_width: Optional[int] = None,
        resize_max_height: Optional[int] = None,
        target_size_kb: Optional[int] = None,
    ) -> None:
        """Asynchronously dispatches batch to worker pool."""
        def run_all():
            for image_id, filename, raw_bytes in files_data:
                cls.process_image_task(
                    batch_id=batch_id,
                    image_id=image_id,
                    filename=filename,
                    raw_bytes=raw_bytes,
                    mode=mode,
                    target_format=target_format,
                    quality=quality,
                    keep_metadata=keep_metadata,
                    resize_max_width=resize_max_width,
                    resize_max_height=resize_max_height,
                    target_size_kb=target_size_kb,
                )
            cls.finalize_batch(batch_id)

        executor.submit(run_all)

    @staticmethod
    def get_batch_status(batch_id: str) -> Optional[Dict[str, Any]]:
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM upload_batches WHERE id = ?", (batch_id,))
            row = cur.fetchone()
            if not row:
                return None
            return dict(row)

    @staticmethod
    def get_batch_results(batch_id: str) -> List[Dict[str, Any]]:
        with db_session() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 
                    u.id as image_id,
                    u.original_filename,
                    u.original_format,
                    u.original_size,
                    u.original_width,
                    u.original_height,
                    u.status as processing_status,
                    u.error_message,
                    r.output_filename,
                    r.output_format,
                    r.output_size,
                    r.output_width,
                    r.output_height,
                    r.bytes_saved,
                    r.percentage_saved,
                    r.ssim_score,
                    r.psnr_score,
                    r.storage_path
                FROM uploaded_images u
                LEFT JOIN optimization_results r ON u.id = r.image_id
                WHERE u.batch_id = ?
                ORDER BY u.created_at ASC
                """,
                (batch_id,),
            )
            return [dict(r) for r in cur.fetchall()]


jobs_service = JobService()

