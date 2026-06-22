"""
AI ä�� ����� (���� ���պ�)
"""
import os
import tempfile
import aiofiles
import httpx
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import ai_handler

router = APIRouter()

class TextRequest(BaseModel):
    text: str


async def forward_to_raspberry(audio_base64: str):
    """����� ���� ����Ŀ ����(5000�� ��Ʈ)�� ������� �����ϴ� ���� �Լ�"""
    if not audio_base64:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://localhost:5000/play", 
                json={"audio_bytes": audio_base64}, 
                timeout=5.0
            )
            print("[+] ����� ���� ����Ŀ ������ ����� ���� ����!")
    except Exception as pi_err:
        print(f"[-] ����� ���� ����Ŀ�� ����� ���� ����: {pi_err}")


@router.post("/text", summary="�ؽ�Ʈ ��û ó�� (�ۿ��� �ؽ�Ʈ ���� �ÿ��� ���� ����Ŀ ����)")
async def chat_text(body: TextRequest):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="�ؽ�Ʈ�� ����ֽ��ϴ�.")
    try:
        # 1. �ؽ�Ʈ �Է��� �޾� AI �亯 �� TTS(�����) ����
        result = await ai_handler.handle_text_input(body.text)
        audio_base64 = result.get("audio_bytes")

        # ?? [���Ⱑ �ٽ�!] ���� �ؽ�Ʈ�� ��û�ص� ����� ���� 5000�� ��Ʈ�� ����� ���� �佺!
        await forward_to_raspberry(audio_base64)

        return JSONResponse(content={
            "user_text": body.text,
            "text_reply": result.get("text_reply", ""),
            "audio_bytes": audio_base64
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ó�� ����: {str(e)}")


@router.post("/audio", summary="���� ���� ó��")
async def chat_audio(file: UploadFile = File(...)):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(file.filename).suffix
        ) as tmp:
            temp_path = tmp.name

        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(await file.read())

        result = await ai_handler.handle_audio_input(temp_path)
        audio_base64 = result.get("audio_bytes")

        # ����� ���� 5000�� ��Ʈ�� ����� �佺
        await forward_to_raspberry(audio_base64)

        return JSONResponse(content={
            "user_text": result["user_text"],
            "text_reply": result["text_reply"],
            "audio_bytes": audio_base64
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"���� ó�� ����: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)