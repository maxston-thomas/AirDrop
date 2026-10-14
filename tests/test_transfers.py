"""
AirLink - Transfer, Checksum, and History Tests
Tests file upload, download, SHA-256 verification, oversized file rejection,
transfer history, and temporary file cleanup.
"""

import hashlib
import io
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import TRANSFERS_DIR
from app.security import session_manager
from app.checksum import calculate_sha256_file, verify_sha256
from app.history import history_manager
from app.transfer_manager import transfer_manager


@pytest.mark.asyncio
async def test_file_upload_and_sha256_verification():
    """Uploads a test file, checks streaming SHA-256, and verifies checksum comparison."""
    transport = ASGITransport(app=app)
    auth_header = {"Authorization": f"Bearer {session_manager.host_token}"}

    file_content = b"AirLink offline Wi-Fi file transfer test payload - 1234567890."
    expected_sha256 = hashlib.sha256(file_content).hexdigest()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Upload with valid sender checksum
        response = await client.post(
            "/api/uploads",
            files={"file": ("test_doc.txt", file_content, "text/plain")},
            data={"sender_sha256": expected_sha256, "direction": "phone_to_laptop"},
            headers=auth_header
        )
        assert response.status_code == 200
        data = response.json()

        assert data["filename"].startswith("test_doc")
        assert data["file_size"] == len(file_content)
        assert data["sha256"] == expected_sha256
        assert data["verified"] is True
        assert "Verified" in data["verification_status"]

        # Verify physical file exists in transfers directory
        saved_file = TRANSFERS_DIR / data["filename"]
        assert saved_file.is_file()
        assert calculate_sha256_file(saved_file) == expected_sha256


@pytest.mark.asyncio
async def test_upload_with_mismatched_checksum():
    """Upload with a wrong sender hash must be flagged as unverified / mismatch."""
    transport = ASGITransport(app=app)
    auth_header = {"Authorization": f"Bearer {session_manager.host_token}"}

    file_content = b"Some data"
    fake_sha256 = "0" * 64

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/uploads",
            files={"file": ("corrupt_file.bin", file_content, "application/octet-stream")},
            data={"sender_sha256": fake_sha256, "direction": "phone_to_laptop"},
            headers=auth_header
        )
        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is False
        assert "Mismatch" in data["verification_status"]


@pytest.mark.asyncio
async def test_staging_and_downloading_file():
    """Host stages a file and client downloads it with headers and checksum."""
    transport = ASGITransport(app=app)
    auth_header = {"Authorization": f"Bearer {session_manager.host_token}"}

    file_content = b"Downloadable report content for mobile device."
    content_sha256 = hashlib.sha256(file_content).hexdigest()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Host stages the file
        stage_resp = await client.post(
            "/api/stage-files",
            files={"files": ("report.pdf", file_content, "application/pdf")},
            headers=auth_header
        )
        assert stage_resp.status_code == 200
        staged_items = stage_resp.json()["staged"]
        assert len(staged_items) == 1
        file_id = staged_items[0]["file_id"]
        assert staged_items[0]["sha256"] == content_sha256

        # 2. Client lists available files
        list_resp = await client.get("/api/files", headers=auth_header)
        assert list_resp.status_code == 200
        files = list_resp.json()["files"]
        assert any(f["file_id"] == file_id for f in files)

        # 3. Client downloads the file
        download_resp = await client.get(
            f"/api/files/{file_id}/download",
            headers=auth_header
        )
        assert download_resp.status_code == 200
        assert download_resp.content == file_content
        assert download_resp.headers.get("X-Checksum-SHA256") == content_sha256
        assert staged_items[0]["filename"] in download_resp.headers.get("Content-Disposition", "")

        # 4. Host unstages the file
        unstage_resp = await client.delete(
            f"/api/files/{file_id}",
            headers=auth_header
        )
        assert unstage_resp.status_code == 200


@pytest.mark.asyncio
async def test_oversized_file_rejection(monkeypatch):
    """Files exceeding maximum allowed upload size must be rejected with HTTP 413 and cleaned up."""
    import app.transfer_manager as tm
    monkeypatch.setattr(tm, "MAX_UPLOAD_SIZE", 64)  # 64 bytes limit

    transport = ASGITransport(app=app)
    auth_header = {"Authorization": f"Bearer {session_manager.host_token}"}
    large_payload = b"X" * 1024  # 1 KB (exceeds 64 bytes limit)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/uploads",
            files={"file": ("huge_file.dat", large_payload, "application/octet-stream")},
            headers=auth_header
        )
        assert response.status_code == 413
        assert "exceeds maximum allowed size" in response.json()["detail"]

        # Ensure no leftover .tmp file
        assert len(list(TRANSFERS_DIR.glob("*huge_file*.tmp"))) == 0


@pytest.mark.asyncio
async def test_transfer_history_recording_and_clearing():
    """Verify history recording and clear operations."""
    transport = ASGITransport(app=app)
    auth_header = {"Authorization": f"Bearer {session_manager.host_token}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Retrieve history
        hist_resp = await client.get("/api/transfers", headers=auth_header)
        assert hist_resp.status_code == 200
        records = hist_resp.json()["history"]
        assert isinstance(records, list)

        # Clear history
        clear_resp = await client.delete("/api/transfers", headers=auth_header)
        assert clear_resp.status_code == 200
        assert clear_resp.json()["success"] is True

        # Verify history is now empty
        empty_resp = await client.get("/api/transfers", headers=auth_header)
        assert empty_resp.json()["count"] == 0


def test_cleanup_incomplete_uploads():
    """Ensures orphaned .tmp files are cleaned up correctly."""
    temp_file = TRANSFERS_DIR / "abandoned_upload.tmp"
    temp_file.write_text("incomplete content")
    assert temp_file.is_file()

    removed_count = transfer_manager.cleanup_temp_files()
    assert removed_count >= 1
    assert not temp_file.exists()
