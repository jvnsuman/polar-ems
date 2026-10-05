"""Main FastAPI application for Polar EMS Edge PC service."""

import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .routes import router

app = FastAPI(
    title="POLAR EMS - Edge Energy Management System",
    description="AI-Driven Smart Energy Management System for Polar Research Stations (SIH26061)",
    version="1.0.0"
)

# Enable CORS for local dashboards and network edge panels
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST routes
app.include_router(router)

# Mount static files directory
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "POLAR EMS Edge Backend Running. Visit /api/status or /docs."}

# WebSocket for live telemetry streaming
@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        from .routes import get_status
        while True:
            status_data = get_status()
            await websocket.send_json(status_data)
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
