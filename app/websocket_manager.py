"""
AirLink - WebSocket Manager
Handles real-time communication between laptop host and connected mobile phones
for live transfer progress, pairing requests, and session updates.
"""

import json
from typing import Set, Dict, Optional
from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    def __init__(self):
        # All active WebSocket connections
        self.active_connections: Set[WebSocket] = set()
        # Mapping from WebSocket to session metadata: {ws: {"token": str, "role": str}}
        self.connection_meta: Dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket, token: Optional[str] = None, role: str = "guest") -> None:
        """Accepts a WebSocket connection and registers session metadata."""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.connection_meta[websocket] = {"token": token, "role": role}

    def disconnect(self, websocket: WebSocket) -> None:
        """Removes a disconnected WebSocket from active tracking."""
        self.active_connections.discard(websocket)
        self.connection_meta.pop(websocket, None)

    def update_role(self, websocket: WebSocket, token: str, role: str) -> None:
        """Updates the session role after successful pairing approval."""
        if websocket in self.connection_meta:
            self.connection_meta[websocket] = {"token": token, "role": role}

    async def broadcast(self, message: dict) -> None:
        """Broadcasts a JSON message to all connected clients."""
        payload = json.dumps(message)
        dead_connections = set()
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.add(connection)

        for dead in dead_connections:
            self.disconnect(dead)

    async def broadcast_to_hosts(self, message: dict) -> None:
        """Sends a JSON message specifically to host laptop sessions."""
        payload = json.dumps(message)
        dead_connections = set()
        for connection, meta in list(self.connection_meta.items()):
            if meta.get("role") == "host":
                try:
                    await connection.send_text(payload)
                except Exception:
                    dead_connections.add(connection)

        for dead in dead_connections:
            self.disconnect(dead)

    async def send_to_token(self, token: str, message: dict) -> None:
        """Sends a message to the specific connection associated with a token."""
        payload = json.dumps(message)
        dead_connections = set()
        for connection, meta in list(self.connection_meta.items()):
            if meta.get("token") == token:
                try:
                    await connection.send_text(payload)
                except Exception:
                    dead_connections.add(connection)

        for dead in dead_connections:
            self.disconnect(dead)


# Global WebSocket connection manager instance
ws_manager = ConnectionManager()
