"""
AirLink - Application Configuration
Configures network settings, storage paths, security constraints, and transfer limits.
"""

import os
import secrets
from pathlib import Path
from pydantic import BaseModel

# Base directory for the AirLink application
BASE_DIR = Path(__file__).resolve().parent.parent

# Storage directory for received and temporary files
TRANSFERS_DIR = BASE_DIR / "transfers"
TRANSFERS_DIR.mkdir(parents=True, exist_ok=True)

# Templates and Static directories
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# SQLite transfer history database path
DATABASE_PATH = BASE_DIR / "transfers.db"

# Server network binding
DEFAULT_HOST = os.getenv("AIRLINK_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("AIRLINK_PORT", "8000"))

# Transfer constraints
# Default: 2 GB maximum upload size
MAX_UPLOAD_SIZE = int(os.getenv("AIRLINK_MAX_UPLOAD_SIZE", 2 * 1024 * 1024 * 1024))
# Chunk size for streaming file I/O (64 KB)
CHUNK_SIZE = 64 * 1024

# Security parameters
# Pairing code expiration in seconds (default 5 minutes)
PAIRING_CODE_EXPIRY_SECONDS = int(os.getenv("AIRLINK_PAIRING_EXPIRY", "300"))
# Authenticated session token expiration in seconds (default 12 hours)
SESSION_EXPIRY_SECONDS = int(os.getenv("AIRLINK_SESSION_EXPIRY", str(12 * 3600)))

# Ephemeral secret key generated per server lifecycle for session token HMAC
SECRET_KEY = os.getenv("AIRLINK_SECRET_KEY", secrets.token_hex(32))

# Application Version
APP_VERSION = "2.0.0"
APP_NAME = "AirDrop"


class AppSettings(BaseModel):
    app_name: str = APP_NAME
    version: str = APP_VERSION
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    max_upload_size: int = MAX_UPLOAD_SIZE
    chunk_size: int = CHUNK_SIZE
    pairing_expiry: int = PAIRING_CODE_EXPIRY_SECONDS
    session_expiry: int = SESSION_EXPIRY_SECONDS


settings = AppSettings()
