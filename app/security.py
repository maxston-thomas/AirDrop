"""
AirLink - Security, Device Pairing, and Path Traversal Protection
Implements cryptographic pairing, token management, session state verification,
and strict filename sanitization against path traversal attacks.
"""

import os
import re
import time
import secrets
import unicodedata
from pathlib import Path
from typing import Dict, Optional, Tuple
from fastapi import Request, HTTPException, status
from app.config import settings

# Windows reserved device names that must never be used as filenames
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}


def sanitize_filename(filename: str) -> str:
    """
    Sanitizes an uploaded or staged filename to completely eliminate path traversal
    and illegal filesystem character vulnerabilities across Windows, Linux, and macOS.
    """
    if not filename:
        return "unnamed_file"

    # Strip directory separators and null bytes
    clean = filename.replace("\\", "/").split("/")[-1]
    clean = clean.replace("\0", "")

    # Normalize unicode characters
    clean = unicodedata.normalize("NFKD", clean)

    # Remove illegal Windows characters: < > : " / \ | ? *
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", clean)

    # Strip leading/trailing dots and whitespace
    clean = clean.strip(". ")

    if not clean:
        clean = "airlink_file"

    # Split stem and extension
    parts = clean.rsplit(".", 1)
    stem = parts[0]
    ext = f".{parts[1]}" if len(parts) > 1 else ""

    # Check for Windows reserved device names
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"file_{stem}"

    # Truncate length if excessively long (max 200 chars stem + ext)
    if len(stem) > 200:
        stem = stem[:200]

    return f"{stem}{ext}"


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """
    Strictly verifies that target_path resolves inside base_dir to prevent directory traversal.
    """
    try:
        resolved_base = base_dir.resolve()
        resolved_target = target_path.resolve()
        return resolved_base in resolved_target.parents or resolved_base == resolved_target
    except Exception:
        return False


def parse_device_info(user_agent: str, client_ip: str) -> dict:
    """Extracts clean, human-friendly device and browser metadata from User-Agent string."""
    ua = user_agent.lower()
    device_type = "Desktop"
    device_name = "Device"
    icon = "desktop"

    if "iphone" in ua:
        device_type = "iPhone"
        device_name = "iPhone"
        icon = "smartphone"
    elif "ipad" in ua:
        device_type = "iPad"
        device_name = "iPad"
        icon = "tablet"
    elif "android" in ua:
        device_type = "Android Phone"
        device_name = "Android Phone"
        icon = "smartphone"
        if "pixel" in ua:
            device_name = "Google Pixel"
        elif "samsung" in ua or "sm-" in ua:
            device_name = "Samsung Galaxy"
    elif "macintosh" in ua or "mac os" in ua:
        device_type = "Mac"
        device_name = "MacBook / Mac"
        icon = "laptop"
    elif "windows" in ua:
        device_type = "Windows PC"
        device_name = "Windows PC"
        icon = "laptop"

    browser = "Browser"
    if "edg/" in ua:
        browser = "Microsoft Edge"
    elif "chrome/" in ua and "crios/" not in ua:
        browser = "Chrome"
    elif "crios/" in ua:
        browser = "Chrome for iOS"
    elif "safari/" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox/" in ua or "fxios/" in ua:
        browser = "Firefox"

    return {
        "device_type": device_type,
        "device_name": device_name,
        "browser": browser,
        "icon": icon,
        "client_ip": client_ip
    }


class PairingRequest:
    def __init__(self, request_id: str, client_ip: str, user_agent: str, code: str):
        self.request_id = request_id
        self.client_ip = client_ip
        self.user_agent = user_agent
        self.code = code
        self.status = "pending"  # pending, approved, rejected, expired
        self.created_at = time.time()
        self.auth_token: Optional[str] = None
        self.device_info = parse_device_info(user_agent, client_ip)

    def is_expired(self, expiry_seconds: int = 300) -> bool:
        return (time.time() - self.created_at) > expiry_seconds

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "device_info": self.device_info,
            "status": self.status,
            "created_at": self.created_at
        }


class SessionManager:
    """
    Manages active sessions, pairing codes, host master key, and client authorizations.
    """

    def __init__(self):
        # Host master token created per server instance
        self.host_token = secrets.token_urlsafe(32)
        # 6-digit active pairing code for mobile devices
        self.current_pairing_code = self._generate_code()
        self.pairing_code_created_at = time.time()
        # Pending and past pairing requests: {request_id: PairingRequest}
        self.pairing_requests: Dict[str, PairingRequest] = {}
        # Authenticated client sessions: {token: {role, client_ip, user_agent, created_at, expires_at}}
        self.active_sessions: Dict[str, dict] = {
            self.host_token: {
                "role": "host",
                "client_ip": "127.0.0.1",
                "user_agent": "AirLink Host Laptop",
                "created_at": time.time(),
                "expires_at": float("inf")
            }
        }

    def _generate_code(self) -> str:
        """Generates a random 6-digit pairing code (e.g., '529148')."""
        return f"{secrets.randbelow(900000) + 100000}"

    def get_pairing_code(self) -> Tuple[str, int]:
        """Returns the current pairing code and remaining seconds before expiry."""
        elapsed = time.time() - self.pairing_code_created_at
        remaining = max(0, int(settings.pairing_expiry - elapsed))
        if remaining == 0:
            self.regenerate_pairing_code()
            remaining = settings.pairing_expiry
        return self.current_pairing_code, remaining

    def regenerate_pairing_code(self) -> str:
        """Generates a new pairing code and invalidates older unused requests."""
        self.current_pairing_code = self._generate_code()
        self.pairing_code_created_at = time.time()
        # Expire any pending pairing requests
        for req in self.pairing_requests.values():
            if req.status == "pending":
                req.status = "expired"
        return self.current_pairing_code

    def submit_pairing_request(self, code: str, client_ip: str, user_agent: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validates client-submitted code.
        Returns: (success, message, request_id)
        """
        # Check code expiry
        current_code, remaining = self.get_pairing_code()
        if remaining <= 0:
            return False, "Pairing code has expired. Please check laptop for new code.", None

        # Clean input
        submitted = re.sub(r"\s+|-", "", code)
        if submitted != current_code:
            return False, "Incorrect pairing code. Please enter the 6 digits shown on the laptop.", None

        request_id = secrets.token_hex(16)
        req = PairingRequest(request_id, client_ip, user_agent, submitted)
        self.pairing_requests[request_id] = req
        return True, "Pairing code accepted. Awaiting host approval on laptop.", request_id

    def approve_pairing_request(self, request_id: str) -> Tuple[bool, Optional[str]]:
        """Host approves client pairing; generates a secure session token."""
        req = self.pairing_requests.get(request_id)
        if not req:
            return False, None
        if req.is_expired(settings.pairing_expiry):
            req.status = "expired"
            return False, None

        token = secrets.token_urlsafe(32)
        req.status = "approved"
        req.auth_token = token

        device_info = parse_device_info(req.user_agent, req.client_ip)
        self.active_sessions[token] = {
            "token": token,
            "role": "client",
            "client_ip": req.client_ip,
            "user_agent": req.user_agent,
            "device_info": device_info,
            "created_at": time.time(),
            "last_seen": time.time(),
            "expires_at": time.time() + settings.session_expiry,
            "is_connected": False
        }
        return True, token

    def set_client_connected(self, token: str, is_connected: bool) -> None:
        """Updates the live connection status when WebSocket connects or disconnects."""
        if token in self.active_sessions and self.active_sessions[token].get("role") == "client":
            self.active_sessions[token]["is_connected"] = is_connected
            self.active_sessions[token]["last_seen"] = time.time()

    def update_heartbeat(self, token: str) -> None:
        """Refreshes last seen timestamp for a connected client session."""
        if token in self.active_sessions:
            self.active_sessions[token]["last_seen"] = time.time()

    def get_connected_devices(self) -> list:
        """Returns list of currently active authenticated client devices."""
        now = time.time()
        connected = []
        for token, s in self.active_sessions.items():
            if s.get("role") == "client":
                is_active = s.get("is_connected", False) or (now - s.get("last_seen", 0) < 30)
                if is_active and now < s.get("expires_at", float("inf")):
                    connected.append({
                        "client_ip": s.get("client_ip"),
                        "user_agent": s.get("user_agent"),
                        "device_info": s.get("device_info", parse_device_info(s.get("user_agent", ""), s.get("client_ip", ""))),
                        "connected_at": s.get("created_at"),
                        "last_seen": s.get("last_seen", s.get("created_at")),
                        "connected_duration_seconds": round(now - s.get("created_at", now), 0)
                    })
        return connected

    def reject_pairing_request(self, request_id: str) -> bool:
        """Host rejects client pairing."""
        req = self.pairing_requests.get(request_id)
        if not req:
            return False
        req.status = "rejected"
        return True

    def get_request_status(self, request_id: str) -> dict:
        """Poll pairing status for client waiting for approval."""
        req = self.pairing_requests.get(request_id)
        if not req:
            return {"status": "not_found"}
        if req.status == "pending" and req.is_expired(settings.pairing_expiry):
            req.status = "expired"

        return {
            "status": req.status,
            "token": req.auth_token if req.status == "approved" else None
        }

    def validate_session(self, token: Optional[str]) -> Optional[dict]:
        """Validates token and returns session metadata if active and not expired."""
        if not token:
            return None
        session = self.active_sessions.get(token)
        if not session:
            return None
        if time.time() > session["expires_at"]:
            del self.active_sessions[token]
            return None
        return session

    def revoke_session(self, token: str) -> bool:
        """Invalidates a session token (disconnect)."""
        if token in self.active_sessions:
            del self.active_sessions[token]
            return True
        return False

    def get_pending_requests(self) -> list:
        """Returns list of pending pairing requests for host dashboard."""
        return [
            req.to_dict()
            for req in self.pairing_requests.values()
            if req.status == "pending" and not req.is_expired(settings.pairing_expiry)
        ]


# Global session manager instance
session_manager = SessionManager()


def extract_token_from_request(request: Request) -> Optional[str]:
    """Extracts authentication token from Authorization header, Cookie, or query param."""
    # 1. Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # 2. X-AirLink-Token header
    custom_header = request.headers.get("X-AirLink-Token")
    if custom_header:
        return custom_header.strip()

    # 3. Cookie
    cookie_token = request.cookies.get("airlink_token")
    if cookie_token:
        return cookie_token.strip()

    # 4. Query param
    query_token = request.query_params.get("token")
    if query_token:
        return query_token.strip()

    return None


async def get_current_session(request: Request) -> Optional[dict]:
    """Dependency that returns the session dictionary or None if unauthenticated."""
    token = extract_token_from_request(request)
    if token:
        # If token was supplied, it must be strictly valid
        return session_manager.validate_session(token)

    # Only if NO token was supplied, check if local loopback host
    client_host = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "")
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return session_manager.active_sessions.get(session_manager.host_token)

    return None


async def require_auth(request: Request) -> dict:
    """Dependency requiring either authenticated client or host session."""
    session = await get_current_session(request)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Device pairing required. Please pair with the laptop."
        )
    return session


async def require_host(request: Request) -> dict:
    """Dependency requiring host privileges."""
    client_host = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "")
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return session_manager.active_sessions.get(session_manager.host_token)

    session = await get_current_session(request)
    if not session or session.get("role") != "host":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Host privileges required."
        )
    return session
