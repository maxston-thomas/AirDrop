"""
AirLink - Transfer History Manager
Maintains a local SQLite database of transfer records with metadata,
transfer speed, SHA-256 checksums, and integrity verification status.
Never exposes absolute server filesystem paths to remote clients.
"""

import sqlite3
import datetime
from pathlib import Path
from typing import List, Dict, Optional
from app.config import DATABASE_PATH


def format_bytes(num_bytes: int) -> str:
    """Formats bytes into human-readable strings (KB, MB, GB)."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_speed(bps: float) -> str:
    """Formats transfer speed in KB/s or MB/s."""
    if bps < 1024:
        return f"{bps:.0f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    else:
        return f"{bps / (1024 * 1024):.2f} MB/s"


class HistoryManager:
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes the SQLite schema if not already present."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transfer_id TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    speed_bps REAL NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    sender_hash TEXT,
                    verified INTEGER NOT NULL,
                    storage_name TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def add_transfer(
        self,
        transfer_id: str,
        filename: str,
        file_size: int,
        direction: str,
        status: str,
        duration_seconds: float,
        speed_bps: float,
        sha256_hash: str,
        sender_hash: Optional[str] = None,
        verified: bool = False,
        storage_name: Optional[str] = None
    ) -> None:
        """Records a new completed or failed transfer event."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO transfers (
                    transfer_id, filename, file_size, direction, status,
                    duration_seconds, speed_bps, sha256_hash, sender_hash,
                    verified, storage_name, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transfer_id,
                filename,
                file_size,
                direction,
                status,
                round(duration_seconds, 2),
                round(speed_bps, 2),
                sha256_hash,
                sender_hash,
                1 if verified else 0,
                storage_name,
                now_iso
            ))
            conn.commit()

    def get_history(self, limit: int = 50) -> List[Dict]:
        """Fetches recent transfer history formatted for client consumption."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM transfers ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                speed_str = format_speed(r["speed_bps"])
                size_str = format_bytes(r["file_size"])
                duration_str = f"{r['duration_seconds']:.1f}s"
                results.append({
                    "id": r["id"],
                    "transfer_id": r["transfer_id"],
                    "filename": r["filename"],
                    "file_size": r["file_size"],
                    "file_size_formatted": size_str,
                    "direction": r["direction"],
                    "status": r["status"],
                    "duration_seconds": r["duration_seconds"],
                    "duration_formatted": duration_str,
                    "speed_bps": r["speed_bps"],
                    "speed_formatted": speed_str,
                    "sha256_hash": r["sha256_hash"],
                    "sender_hash": r["sender_hash"],
                    "verified": bool(r["verified"]),
                    "has_local_file": bool(r["storage_name"]),
                    "timestamp": r["timestamp"]
                })
            return results

    def get_transfer_by_id(self, transfer_id: str) -> Optional[Dict]:
        """Fetches a specific transfer record by transfer_id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM transfers WHERE transfer_id = ?",
                (transfer_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def clear_history(self) -> None:
        """Clears all transfer history entries."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM transfers")
            conn.commit()


# Global history manager instance
history_manager = HistoryManager()
