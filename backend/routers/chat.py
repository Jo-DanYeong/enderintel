"""
AI ä�� �����
POST /api/chat/text - �ۿ��� �ؽ�Ʈ ���� �� �ؽ�Ʈ ���丸 ��ȯ
POST /api/chat/audio - ���� ���ο� (pi_local���� ���� ȣ��)
"""
import os
import tempfile
import aiofiles
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import ai_handler

router = APIRouter()


class TextRequest(BaseModel):
    text: str


# ��������������������������������������������������������������������������������������������
# �� ���� - �ؽ�Ʈ in / �ؽ�Ʈ out
# ��������������������������������������������������������������������������������������������
@router.post("/text", summary="�ؽ�Ʈ ���� ó�� (�� ����)")
async def chat_text(body: TextRequest):
    """
    �ۿ��� �ؽ�Ʈ�� ��û�ϸ� �ؽ�Ʈ�θ� �����մϴ�.
    ESP32 ��� �ʿ��ϸ� ���������� BLE ó�� �� ����� �ؽ�Ʈ�� �����մϴ�.

    Response: {"user_text": str, "text_reply": str}
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="�ؽ�Ʈ�� ����ֽ��ϴ�.")
    try:
        result = await ai_handler.handle_text_input(body.text)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ó�� ����: {str(e)}")


# ��������������������������������������������������������������������������������������������
# ���� ���ο� - ����� in / �ؽ�Ʈ out
# pi_local/main.py ���� localhost�� ȣ��
# ��������������������������������������������������������������������������������������������
@router.post("/audio", summary="���� ���� ó�� (���� ���ο�)")
async def chat_audio(file: UploadFile = File(...)):
    """
    ���� ����ũ ���� ������ �޾� ó���մϴ�.
    TTS ������� ����Ʈ�� ���� ��ȯ (���� ���� ����).

    Response: {"user_text": str, "text_reply": str}
    (audio_bytes�� pi_local�� ����Ŀ�� ���� ���)
    """
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(file.filename).suffix
        ) as tmp:
            temp_path = tmp.name

        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(await file.read())

        result = await ai_handler.handle_audio_input(temp_path)

        # audio_bytes�� ���信�� ���� (pi_local�� ������ TTS ���)
        return JSONResponse(content={
            "user_text": result["user_text"],
            "text_reply": result["text_reply"],
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"����� ó�� ����: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)