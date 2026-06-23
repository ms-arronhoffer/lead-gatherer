from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, job_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[job_id].append(ws)

    def disconnect(self, job_id: str, ws: WebSocket) -> None:
        try:
            self._connections[job_id].remove(ws)
        except ValueError:
            pass

    async def broadcast(self, job_id: str, event: dict) -> None:
        dead = []
        for ws in list(self._connections.get(job_id, [])):
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(job_id, ws)


manager = ConnectionManager()


@router.websocket("/ws/jobs/{job_id}")
async def ws_job_progress(job_id: str, websocket: WebSocket):
    await manager.connect(job_id, websocket)
    try:
        while True:
            # Keep alive — client can send pings; we just read and discard
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id, websocket)
