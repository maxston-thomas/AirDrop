"""
AirLink - Main FastAPI Application
Serves the offline peer-to-peer file transfer system, REST APIs, and WebSocket endpoints.
Binds to 0.0.0.0 and operates completely locally without internet access.
"""

import os
import time
from pathlib import Path
from typing import List, Optional
from fastapi import (
    FastAPI, Request, Response, Depends, UploadFile, File, Form,
    HTTPException, status, WebSocket, WebSocketDisconnect
)
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import (
    settings, BASE_DIR, STATIC_DIR, TEMPLATES_DIR, TRANSFERS_DIR,
    APP_NAME, APP_VERSION
)
from app.network import (
    get_local_ip, get_all_network_interfaces, get_access_url,
    generate_qr_code_svg, generate_qr_code_base64_png
)
from app.security import (
    session_manager, sanitize_filename, is_safe_path,
    get_current_session, require_auth, require_host, extract_token_from_request
)
from app.checksum import calculate_sha256_file, verify_sha256
from app.history import history_manager, format_bytes, format_speed
from app.transfer_manager import transfer_manager, StagedFile
from app.websocket_manager import ws_manager

# Application startup timestamp
START_TIME = time.time()

# FastAPI application initialization
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Offline AirDrop-style local Wi-Fi peer-to-peer file transfer system"
)

# Mount static directory for CSS, JavaScript, icons, etc.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Pydantic schemas for request validation
class PairRequestSchema(BaseModel):
    code: str


class PairActionSchema(BaseModel):
    request_id: str


class ClearHistorySchema(BaseModel):
    confirm: bool = True


class TransferNotifyStartSchema(BaseModel):
    transfer_id: str
    filename: str
    file_size: int
    direction: str = "phone_to_laptop"
    sender_device: Optional[str] = "Device"


class TransferNotifyProgressSchema(BaseModel):
    transfer_id: str
    loaded: int
    total: int
    speed: float = 0.0
    eta: Optional[int] = None
    direction: Optional[str] = "phone_to_laptop"


class TransferNotifyCancelSchema(BaseModel):
    transfer_id: str
    reason: Optional[str] = "Cancelled"


# --- HTML Page Routes ---

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """Serves the main AirLink responsive dashboard."""
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend template not found")
    with open(index_file, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)


@app.get("/privacy", response_class=HTMLResponse)
async def serve_privacy():
    """Serves the offline local privacy policy."""
    privacy_file = TEMPLATES_DIR / "privacy.html"
    if not privacy_file.exists():
        raise HTTPException(status_code=404, detail="Privacy template not found")
    with open(privacy_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/terms", response_class=HTMLResponse)
async def serve_terms():
    """Serves the offline local terms of service."""
    terms_file = TEMPLATES_DIR / "terms.html"
    if not terms_file.exists():
        raise HTTPException(status_code=404, detail="Terms template not found")
    with open(terms_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/favicon.svg")
async def serve_favicon_svg():
    """Serves vector SVG favicon."""
    fav_path = STATIC_DIR / "favicon.svg"
    if fav_path.exists():
        return FileResponse(fav_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404)


@app.get("/favicon.ico")
async def serve_favicon_ico():
    """Serves standard favicon."""
    fav_path = STATIC_DIR / "favicon.svg"
    if fav_path.exists():
        return FileResponse(fav_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404)


# --- REST API Endpoints ---

@app.get("/api/health")
async def get_health():
    """System health check and diagnostic information."""
    uptime = time.time() - START_TIME
    return {
        "status": "online",
        "app": APP_NAME,
        "version": APP_VERSION,
        "uptime_seconds": round(uptime, 1),
        "local_ip": get_local_ip(),
        "transfers_dir_exists": TRANSFERS_DIR.exists()
    }


@app.get("/api/network/info")
async def get_network_info():
    """
    Returns detected network interfaces, primary LAN IP, access URL,
    and pairing QR codes in both SVG and PNG data URI formats.
    """
    primary_ip = get_local_ip()
    port = settings.port
    access_url = get_access_url(port=port, ip=primary_ip)
    interfaces = get_all_network_interfaces()

    qr_svg = generate_qr_code_svg(access_url)
    qr_png = generate_qr_code_base64_png(access_url)

    return {
        "primary_ip": primary_ip,
        "port": port,
        "access_url": access_url,
        "interfaces": interfaces,
        "qr_code_svg": qr_svg,
        "qr_code_png": qr_png
    }


@app.get("/api/session/state")
async def get_session_state(request: Request):
    """
    Inspects caller's session state:
    - Host laptop sees pairing code, pending authorization requests, and master controls.
    - Paired client sees authenticated status and permissions.
    - Unpaired guest sees pairing prompt.
    """
    client_ip = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "unknown")

    # If connecting directly from localhost, the laptop is ALWAYS the host!
    if client_ip in ("127.0.0.1", "::1", "localhost"):
        pairing_code, remaining = session_manager.get_pairing_code()
        pending = session_manager.get_pending_requests()
        connected_devices = session_manager.get_connected_devices()
        return {
            "authenticated": True,
            "role": "host",
            "client_ip": client_ip,
            "pairing_code": pairing_code,
            "code_remaining_seconds": remaining,
            "pending_requests": pending,
            "connected_devices": connected_devices,
            "is_device_connected": len(connected_devices) > 0,
            "active_device": connected_devices[0] if connected_devices else None,
            "staged_count": len(transfer_manager.staged_files),
            "host_token": session_manager.host_token
        }

    session = await get_current_session(request)
    if session and session.get("role") == "client":
        return {
            "authenticated": True,
            "role": "client",
            "client_ip": client_ip,
            "device_info": session.get("device_info", {}),
            "staged_count": len(transfer_manager.staged_files)
        }
    else:
        return {
            "authenticated": False,
            "role": "guest",
            "client_ip": client_ip
        }


@app.post("/api/pair/request")
async def submit_pairing_code(payload: PairRequestSchema, request: Request):
    """Mobile phone submits 6-digit pairing code shown on laptop screen."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "Mobile Device")

    success, msg, req_id = session_manager.submit_pairing_request(
        code=payload.code,
        client_ip=client_ip,
        user_agent=user_agent
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # Notify host laptop via WebSocket in real-time
    await ws_manager.broadcast({
        "event": "pairing_requested",
        "data": {
            "request_id": req_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "code": payload.code
        }
    })

    return {
        "success": True,
        "message": msg,
        "request_id": req_id
    }


@app.get("/api/pair/status/{request_id}")
async def check_pairing_status(request_id: str):
    """Mobile client polls status of its pairing request until host approves/rejects."""
    status_dict = session_manager.get_request_status(request_id)
    return status_dict


@app.post("/api/pair/approve")
async def approve_pairing(payload: PairActionSchema, session: dict = Depends(require_host)):
    """Host approves a pending pairing request."""
    success, token = session_manager.approve_pairing_request(payload.request_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request not found or has expired"
        )

    # Notify all clients via WebSocket
    await ws_manager.broadcast({
        "event": "pairing_decision",
        "data": {
            "request_id": payload.request_id,
            "status": "approved",
            "token": token
        }
    })

    return {"success": True, "token": token}


@app.post("/api/pair/reject")
async def reject_pairing(payload: PairActionSchema, session: dict = Depends(require_host)):
    """Host rejects a pending pairing request."""
    success = session_manager.reject_pairing_request(payload.request_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    await ws_manager.broadcast({
        "event": "pairing_decision",
        "data": {
            "request_id": payload.request_id,
            "status": "rejected"
        }
    })

    return {"success": True}


@app.post("/api/pair/new-code")
async def refresh_pairing_code(session: dict = Depends(require_host)):
    """Regenerates a new 6-digit pairing code on demand."""
    new_code = session_manager.regenerate_pairing_code()
    await ws_manager.broadcast_to_hosts({
        "event": "code_refreshed",
        "data": {
            "pairing_code": new_code,
            "remaining_seconds": settings.pairing_expiry
        }
    })
    return {
        "pairing_code": new_code,
        "remaining_seconds": settings.pairing_expiry
    }


@app.post("/api/session/disconnect")
async def disconnect_session(request: Request):
    """Terminates active session and revokes authentication token."""
    token = extract_token_from_request(request)
    if token:
        session_manager.set_client_connected(token, False)
        session_manager.revoke_session(token)
        await ws_manager.broadcast({
            "event": "session_disconnected",
            "data": {
                "token": token,
                "devices": session_manager.get_connected_devices()
            }
        })
    return {"success": True, "message": "Session terminated"}


# --- File Transfer Endpoints ---

@app.post("/api/stage-files")
async def stage_files_for_download(
    files: List[UploadFile] = File(...),
    session: dict = Depends(require_host)
):
    """
    Host laptop stages one or more files to be made available for download by the phone.
    Computes sender SHA-256 checksum and saves to transfers directory.
    """
    staged_results = []
    for file in files:
        result = await transfer_manager.save_uploaded_stream(
            upload_file=file,
            direction="laptop_to_phone"
        )
        saved_path = TRANSFERS_DIR / result["filename"]
        staged_obj = transfer_manager.stage_file(
            filename=result["filename"],
            file_path=saved_path
        )
        staged_results.append(staged_obj.to_dict())

    # Broadcast to all connected devices that files are staged
    await ws_manager.broadcast({
        "event": "files_staged_updated",
        "data": {"staged_files": transfer_manager.list_staged_files()}
    })

    return {"success": True, "staged": staged_results}


@app.get("/api/files")
async def list_available_files(session: dict = Depends(require_auth)):
    """Lists files currently staged and available for download by authorized devices."""
    return {
        "files": transfer_manager.list_staged_files(),
        "total_count": len(transfer_manager.staged_files)
    }


@app.get("/api/files/{file_id}/download")
async def download_file(file_id: str, session: dict = Depends(require_auth)):
    """
    Streams an authorized staged file for client download.
    Includes sender SHA-256 checksum in X-Checksum-SHA256 response header.
    """
    staged = transfer_manager.get_staged_file(file_id)
    if not staged or not staged.file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested file not found or no longer available"
        )

    # Strictly verify path safety
    if not is_safe_path(TRANSFERS_DIR, staged.file_path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Path traversal prevented"
        )

    headers = {
        "Content-Disposition": f'attachment; filename="{staged.filename}"',
        "Content-Length": str(staged.file_size),
        "X-Checksum-SHA256": staged.sha256,
        "X-AirLink-Filename": staged.filename
    }

    return FileResponse(
        path=staged.file_path,
        media_type=staged.mime_type,
        filename=staged.filename,
        headers=headers
    )


@app.delete("/api/files/{file_id}")
async def unstage_file(file_id: str, session: dict = Depends(require_host)):
    """Host removes a file from the staged downloads list."""
    removed = transfer_manager.unstage_file(file_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    await ws_manager.broadcast({
        "event": "files_staged_updated",
        "data": {"staged_files": transfer_manager.list_staged_files()}
    })

    return {"success": True}


@app.post("/api/uploads")
async def upload_file(
    file: UploadFile = File(...),
    transfer_id: Optional[str] = Form(None),
    sender_sha256: Optional[str] = Form(None),
    direction: Optional[str] = Form("phone_to_laptop"),
    session: dict = Depends(require_auth)
):
    """
    Receives an uploaded file from mobile phone or laptop.
    Streams to isolated temporary file, calculates SHA-256 hash,
    compares against sender hash if provided, and records transfer history.
    """
    result = await transfer_manager.save_uploaded_stream(
        upload_file=file,
        sender_sha256=sender_sha256,
        direction=direction or "phone_to_laptop",
        transfer_id=transfer_id
    )

    if direction == "laptop_to_phone":
        saved_path = TRANSFERS_DIR / result["filename"]
        transfer_manager.stage_file(
            filename=result["filename"],
            file_path=saved_path
        )
        await ws_manager.broadcast({
            "event": "files_staged_updated",
            "data": {"staged_files": transfer_manager.list_staged_files()}
        })

    # Notify all devices of completed upload and updated history
    await ws_manager.broadcast({
        "event": "transfer_completed",
        "data": result
    })

    return result


@app.post("/api/transfers/notify-start")
async def notify_transfer_start(payload: TransferNotifyStartSchema, session: dict = Depends(require_auth)):
    """Broadcasts to all connected devices that a file transfer has initiated."""
    await ws_manager.broadcast({
        "event": "transfer_started",
        "data": payload.model_dump()
    })
    return {"success": True}


@app.post("/api/transfers/notify-progress")
async def notify_transfer_progress(payload: TransferNotifyProgressSchema, session: dict = Depends(require_auth)):
    """Broadcasts real-time upload progress to the receiving device."""
    await ws_manager.broadcast({
        "event": "transfer_progress",
        "data": payload.model_dump()
    })
    return {"success": True}


@app.post("/api/transfers/notify-cancel")
async def notify_transfer_cancel(payload: TransferNotifyCancelSchema, session: dict = Depends(require_auth)):
    """Broadcasts transfer cancellation."""
    await ws_manager.broadcast({
        "event": "transfer_failed",
        "data": payload.model_dump()
    })
    return {"success": True}


@app.get("/api/transfers")
async def get_transfer_history(session: dict = Depends(require_auth)):
    """Retrieves list of past file transfers with speed, size, and SHA-256 verification."""
    history = history_manager.get_history(limit=100)
    return {"history": history, "count": len(history)}


@app.delete("/api/transfers")
async def clear_transfer_history(session: dict = Depends(require_host)):
    """Clears transfer history database records."""
    history_manager.clear_history()
    await ws_manager.broadcast({
        "event": "history_cleared",
        "data": {}
    })
    return {"success": True, "message": "Transfer history cleared"}


@app.get("/api/transfers/{transfer_id}/download")
async def download_history_file(transfer_id: str, session: dict = Depends(require_auth)):
    """Allows downloading a previously received file stored in the local transfers folder."""
    record = history_manager.get_transfer_by_id(transfer_id)
    if not record or not record.get("storage_name"):
        raise HTTPException(status_code=404, detail="Transfer record or file not found")

    storage_name = record["storage_name"]
    file_path = TRANSFERS_DIR / storage_name

    if not file_path.is_file() or not is_safe_path(TRANSFERS_DIR, file_path):
        raise HTTPException(status_code=404, detail="Physical file no longer exists")

    return FileResponse(
        path=file_path,
        filename=record["filename"],
        headers={"X-Checksum-SHA256": record["sha256_hash"]}
    )


# --- WebSocket Endpoint ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time live transfer progress, pairing requests,
    and instantaneous cross-device status synchronization.
    """
    token = websocket.query_params.get("token")
    session = session_manager.validate_session(token)
    client_host = websocket.client.host if websocket.client else ""
    if not session and client_host in ("127.0.0.1", "::1", "localhost"):
        session = session_manager.active_sessions.get(session_manager.host_token)
        token = session_manager.host_token
    role = session["role"] if session else "guest"

    await ws_manager.connect(websocket, token=token, role=role)

    # If an authenticated mobile client connects, update status and broadcast to host
    if role == "client" and token:
        session_manager.set_client_connected(token, True)
        devs = session_manager.get_connected_devices()
        active_dev = devs[0] if devs else None
        await ws_manager.broadcast({
            "event": "device_connected",
            "data": {
                "device": active_dev,
                "devices": devs
            }
        })

    try:
        while True:
            data = await websocket.receive_text()
            # Handle client-side heartbeat or ping
            if data == "ping":
                if token:
                    session_manager.update_heartbeat(token)
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        if role == "client" and token:
            session_manager.set_client_connected(token, False)
            devs = session_manager.get_connected_devices()
            await ws_manager.broadcast({
                "event": "device_disconnected",
                "data": {
                    "device": None,
                    "devices": devs
                }
            })
    except Exception:
        ws_manager.disconnect(websocket)
        if role == "client" and token:
            session_manager.set_client_connected(token, False)
            devs = session_manager.get_connected_devices()
            await ws_manager.broadcast({
                "event": "device_disconnected",
                "data": {
                    "device": None,
                    "devices": devs
                }
            })
