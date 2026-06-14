"""
Ender-Intel FastAPI �鿣�� ����
�� �� ���� ��� + ESP32 BLE ����
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from .routers import chat, manual
from .bluetooth_integration import start_bluetooth_server, stop_bluetooth_server
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("static/audio", exist_ok=True)
    print("? Ender-Intel �鿣�� ���� ����")
    # Start Bluetooth RFCOMM server (if available)
    try:
        bt = start_bluetooth_server()
        app.state._bt_thread = bt.get("thread")
        app.state._bt_socket = bt.get("server_socket")
    except Exception as e:
        print(f"[startup] Bluetooth server failed to start: {e}")
    yield
    print("?? ���� ����")
    # Stop Bluetooth server on shutdown
    try:
        stop_bluetooth_server(getattr(app.state, "_bt_socket", None))
    except Exception as e:
        print(f"[shutdown] Bluetooth server stop error: {e}")


app = FastAPI(title="Ender-Intel API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Ensure static directories exist before mounting (FastAPI mounts at import time)
os.makedirs("static", exist_ok=True)
os.makedirs("static/audio", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(chat.router, prefix="/api/chat", tags=["AI ��"])
app.include_router(manual.router, prefix="/api/manual", tags=["���� ����"])


@app.get("/")
async def root():
    return {"status": "ok", "message": "Ender-Intel ���� �۵� ��"}


@app.get("/health")
async def health():
    return {"status": "healthy"}