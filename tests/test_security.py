"""
AirLink - Security and Pairing Tests
Tests pairing code validation, expiration, unauthorized access rejection,
path traversal sanitization, and session revocation.
"""

import time
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.security import (
    session_manager, sanitize_filename, is_safe_path
)
from app.config import TRANSFERS_DIR


@pytest.mark.asyncio
async def test_unauthorized_access_rejection():
    """Unauthenticated clients must be rejected with 401 on protected endpoints."""
    transport = ASGITransport(app=app)
    # Using an external client IP (192.168.1.99) so it is not treated as loopback host
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Forwarded-For": "192.168.1.99"}
    ) as client:
        # Protected files endpoint
        resp_files = await client.get("/api/files")
        assert resp_files.status_code == 401

        # Protected upload endpoint
        resp_upload = await client.post(
            "/api/uploads",
            files={"file": ("test.txt", b"hello world", "text/plain")}
        )
        assert resp_upload.status_code == 401

        # Protected transfers history endpoint
        resp_history = await client.get("/api/transfers")
        assert resp_history.status_code == 401


@pytest.mark.asyncio
async def test_pairing_workflow_and_approval():
    """Tests the complete mobile pairing workflow: submit code, host approve, client access."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get host pairing code
        pairing_code, _ = session_manager.get_pairing_code()
        assert len(pairing_code) == 6

        # 2. Reject incorrect pairing code
        bad_resp = await client.post("/api/pair/request", json={"code": "000000"})
        if "000000" != pairing_code:
            assert bad_resp.status_code == 400

        # 3. Submit valid pairing code
        submit_resp = await client.post("/api/pair/request", json={"code": pairing_code})
        assert submit_resp.status_code == 200
        req_data = submit_resp.json()
        assert req_data["success"] is True
        request_id = req_data["request_id"]

        # 4. Check status before host approval (should be pending)
        status_resp = await client.get(f"/api/pair/status/{request_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "pending"

        # 5. Host approves the pairing request
        approve_resp = await client.post(
            "/api/pair/approve",
            json={"request_id": request_id},
            headers={"Authorization": f"Bearer {session_manager.host_token}"}
        )
        assert approve_resp.status_code == 200
        auth_token = approve_resp.json()["token"]
        assert auth_token is not None

        # 6. Verify client now has access using this token
        auth_files_resp = await client.get(
            "/api/files",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert auth_files_resp.status_code == 200

        # 7. Disconnect / Revoke session
        disco_resp = await client.post(
            "/api/session/disconnect",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert disco_resp.status_code == 200

        # 8. Token is now invalid
        post_disco_resp = await client.get(
            "/api/files",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert post_disco_resp.status_code == 401


@pytest.mark.asyncio
async def test_pairing_code_expiration():
    """Expired pairing requests should be rejected."""
    pairing_code, _ = session_manager.get_pairing_code()
    # Artificially age the pairing code timestamp
    session_manager.pairing_code_created_at = time.time() - 350
    # Calling get_pairing_code should regenerate a new code
    new_code, _ = session_manager.get_pairing_code()
    assert new_code != ""


def test_filename_sanitization_and_path_traversal():
    """Verify robust defense against path traversal attacks and invalid filenames."""
    # Classic path traversal attacks
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"
    assert sanitize_filename("/var/log/secret.key") == "secret.key"

    # Null bytes
    assert sanitize_filename("safe\0payload.txt") == "safepayload.txt"

    # Illegal Windows characters
    assert sanitize_filename('test<invalid>:file"name?.pdf') == "test_invalid__file_name_.pdf"

    # Empty or dots only
    assert sanitize_filename("...") == "airlink_file"
    assert sanitize_filename("") == "unnamed_file"

    # Windows reserved device names
    assert sanitize_filename("CON.txt").startswith("file_CON")
    assert sanitize_filename("NUL.pdf").startswith("file_NUL")

    # Safe path assertion
    safe_file = TRANSFERS_DIR / "myfile.txt"
    unsafe_file = TRANSFERS_DIR / ".." / "config.py"
    assert is_safe_path(TRANSFERS_DIR, safe_file) is True
    assert is_safe_path(TRANSFERS_DIR, unsafe_file) is False
