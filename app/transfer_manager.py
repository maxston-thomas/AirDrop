"""
AirLink - Transfer Manager
Coordinates staged files for laptop-to-phone downloads, streaming uploads with temporary file
isolation, collision-safe storage, on-the-fly SHA-256 computation, and incomplete upload cleanup.
"""

import os
import time
import uuid
import secrets
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from fastapi import UploadFile, HTTPException, status
from app.config import TRANSFERS_DIR, MAX_UPLOAD_SIZE, CHUNK_SIZE
from app.security import sanitize_filename, is_safe_path
from app.checksum import StreamHashTracker, calculate_sha256_file, verify_sha256
from app.history import history_manager, format_bytes, format_speed


class StagedFile:
    def __init__(
        self,
        file_id: str,
        filename: str,
        file_path: Path,
        file_size: int,
        mime_type: str,
        sha256: str
    ):
        self.file_id = file_id
        self.filename = filename
        self.file_path = file_path
        self.file_size = file_size
        self.mime_type = mime_type
        self.sha256 = sha256
        self.created_at = time.time()

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "file_size_formatted": format_bytes(self.file_size),
            "mime_type": self.mime_type,
            "sha256": self.sha256,
            "created_at": self.created_at
        }


class TransferManager:
    def __init__(self, storage_dir: Path = TRANSFERS_DIR):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # In-memory registry of files staged on laptop for phone download: {file_id: StagedFile}
        self.staged_files: Dict[str, StagedFile] = {}
        # Clean up any leftover .tmp files from previous server runs
        self.cleanup_temp_files()

    def cleanup_temp_files(self) -> int:
        """Removes orphaned .tmp files in the transfer directory."""
        removed = 0
        try:
            for item in self.storage_dir.glob("*.tmp"):
                if item.is_file():
                    item.unlink(missing_ok=True)
                    removed += 1
        except Exception:
            pass
        return removed

    def stage_file(self, filename: str, file_path: Path) -> StagedFile:
        """
        Registers an existing local file on the laptop as available for phone download.
        Computes sender SHA-256 checksum in advance.
        """
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {filename}")

        clean_name = sanitize_filename(filename)
        file_size = file_path.stat().st_size
        sha256_hash = calculate_sha256_file(file_path)
        mime_type, _ = mimetypes.guess_type(clean_name)
        if not mime_type:
            mime_type = "application/octet-stream"

        file_id = secrets.token_hex(12)
        staged = StagedFile(
            file_id=file_id,
            filename=clean_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            sha256=sha256_hash
        )
        self.staged_files[file_id] = staged
        return staged

    def unstage_file(self, file_id: str) -> bool:
        """Removes a staged file from the available downloads list."""
        if file_id in self.staged_files:
            del self.staged_files[file_id]
            return True
        return False

    def list_staged_files(self) -> List[dict]:
        """Returns list of files currently staged for phone download."""
        return [sf.to_dict() for sf in self.staged_files.values()]

    def get_staged_file(self, file_id: str) -> Optional[StagedFile]:
        """Retrieves a staged file by its unique identifier."""
        return self.staged_files.get(file_id)

    def _get_unique_destination_path(self, filename: str) -> Path:
        """Generates a collision-safe destination path in the transfers directory."""
        clean_name = sanitize_filename(filename)
        dest = self.storage_dir / clean_name
        if not dest.exists():
            return dest

        parts = clean_name.rsplit(".", 1)
        stem = parts[0]
        ext = f".{parts[1]}" if len(parts) > 1 else ""

        counter = 1
        while True:
            candidate = self.storage_dir / f"{stem}_{counter}{ext}"
            if not candidate.exists():
                return candidate
            counter += 1

    async def save_uploaded_stream(
        self,
        upload_file: UploadFile,
        sender_sha256: Optional[str] = None,
        direction: str = "phone_to_laptop",
        transfer_id: Optional[str] = None
    ) -> dict:
        """
        Streams an incoming file to a temporary file while computing SHA-256 on-the-fly.
        Enforces maximum upload size and guarantees cleanup on failure.
        """
        original_name = upload_file.filename or "uploaded_file"
        clean_name = sanitize_filename(original_name)
        temp_id = str(uuid.uuid4())
        temp_path = self.storage_dir / f"upload_{temp_id}.tmp"

        hash_tracker = StreamHashTracker()
        start_time = time.time()
        bytes_written = 0

        try:
            with open(temp_path, "wb") as f_out:
                while True:
                    chunk = await upload_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > MAX_UPLOAD_SIZE:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File exceeds maximum allowed size of {format_bytes(MAX_UPLOAD_SIZE)}"
                        )
                    f_out.write(chunk)
                    hash_tracker.update(chunk)
        except Exception as e:
            # Clean up temporary file immediately on error or interruption
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Upload failed: {str(e)}"
            )

        # File writing completed successfully
        elapsed_time = max(0.001, time.time() - start_time)
        speed_bps = bytes_written / elapsed_time
        calc_hash = hash_tracker.hex_digest

        # Verify integrity against sender hash if provided
        is_verified, verify_msg = verify_sha256(calc_hash, sender_sha256)

        # Move to safe permanent destination
        final_dest = self._get_unique_destination_path(clean_name)
        temp_path.rename(final_dest)

        tid = transfer_id or secrets.token_hex(12)
        history_manager.add_transfer(
            transfer_id=tid,
            filename=final_dest.name,
            file_size=bytes_written,
            direction=direction,
            status="completed",
            duration_seconds=elapsed_time,
            speed_bps=speed_bps,
            sha256_hash=calc_hash,
            sender_hash=sender_sha256,
            verified=is_verified,
            storage_name=final_dest.name
        )

        return {
            "transfer_id": tid,
            "filename": final_dest.name,
            "file_size": bytes_written,
            "file_size_formatted": format_bytes(bytes_written),
            "sha256": calc_hash,
            "sender_sha256": sender_sha256,
            "verified": is_verified,
            "verification_status": verify_msg,
            "duration_seconds": round(elapsed_time, 2),
            "duration_formatted": f"{elapsed_time:.1f}s",
            "speed_bps": round(speed_bps, 2),
            "speed_formatted": format_speed(speed_bps)
        }


# Global transfer manager instance
transfer_manager = TransferManager()
