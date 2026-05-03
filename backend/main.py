"""
Ender-Intel FastAPI �鿣�� ����
�� �� ���� ��� + ESP32 BLE ����
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from routers import chat, manual


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("static/audio", exist_ok=True)
    print("? Ender-Intel �鿣�� ���� ����")
    yield
    print("?? ���� ����")


app = FastAPI(title="Ender-Intel API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(chat.router, prefix="/api/chat", tags=["AI ��"])
app.include_router(manual.router, prefix="/api/manual", tags=["���� ����"])


@app.get("/")
async def root():
    return {"status": "ok", "message": "Ender-Intel ���� �۵� ��"}


@app.get("/health")
async def health():
    return {"status": "healthy"}