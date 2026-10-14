"""
AirLink - SHA-256 Checksum Calculation and Integrity Verification
Provides streaming cryptographic hashing to ensure end-to-end data integrity
without loading entire large files into system RAM.
"""

import hashlib
import hmac
from pathlib import Path
from typing import Tuple, Optional


def calculate_sha256_file(file_path: Path, chunk_size: int = 65536) -> str:
    """
    Computes the SHA-256 checksum of an existing file on disk using chunked streaming.
    Memory footprint remains constant (~64KB) regardless of file size.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


class StreamHashTracker:
    """
    Tracks SHA-256 hash and byte count incrementally as chunks are received or sent.
    """

    def __init__(self):
        self.hasher = hashlib.sha256()
        self.bytes_processed = 0

    def update(self, chunk: bytes) -> None:
        self.hasher.update(chunk)
        self.bytes_processed += len(chunk)

    @property
    def hex_digest(self) -> str:
        return self.hasher.hexdigest()

    @property
    def total_bytes(self) -> int:
        return self.bytes_processed


def verify_sha256(calculated_hash: str, expected_hash: Optional[str]) -> Tuple[bool, str]:
    """
    Compares the calculated hash with the expected sender hash.
    Uses constant-time comparison to prevent timing side-channels.
    Returns: (is_verified, status_message)
    """
    if not expected_hash:
        return False, "Self-calculated (No sender checksum provided)"

    clean_calc = calculated_hash.strip().lower()
    clean_exp = expected_hash.strip().lower()

    if len(clean_exp) != 64 or not all(c in "0123456789abcdef" for c in clean_exp):
        return False, "Invalid sender checksum format"

    if hmac.compare_digest(clean_calc, clean_exp):
        return True, "Integrity Verified (Sender & Receiver hashes match)"
    else:
        return False, "Integrity Mismatch! File may be corrupt or modified"
