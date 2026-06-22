import asyncio
import os
import base64
from fastapi import FastAPI, Body
import uvicorn

# ���� ����� ��� ��� ��������
from audio_player import play_audio_bytes, play_beep

app = FastAPI(title="Ender-Intel Audio Receiver")

@app.post("/play")
async def play_sound(payload: dict = Body(...)):
    """
    �鿣�� ������ ����Ʈ�� �ۿ��� { "audio_bytes": "Base64���ڿ�" } ������ 
    �����͸� ����� �����ϸ�, ����� ���� ����Ŀ�� ��� ����մϴ�.
    """
    audio_data = payload.get("audio_bytes")
    
    if audio_data:
        print("\n[+] �ܺ�(��/�鿣��)�κ��� ����� ������ ���� �Ϸ�!")
        print("[+] ����Ŀ ����� �����մϴ�...")
        
        # ������ �� �� �︮�� ��� ���
        play_beep(frequency=880, duration=0.15)
        play_audio_bytes(audio_data)
        
        return {"status": "success", "message": "Audio played successfully"}
    
    print("[-] ���� �����Ϳ� ����� ����Ʈ�� �����ϴ�.")
    return {"status": "error", "message": "No audio data found"}

@app.get("/")
async def root():
    return {"status": "online", "message": "Ender-Intel Speaker Server is running"}

if __name__ == "__main__":
    print("\n" + "="*40)
    print("  ?? Ender-Intel ����Ŀ ���� ���� ���� ����")
    print("  ?? ����ũ ���� �ܺ� ����� ����� ����մϴ�.")
    print("="*40 + "\n")
    
    # ����� ������ 5000�� ��Ʈ�� ���� ��� ��� ���� ����
    uvicorn.run(app, host="0.0.0.0", port=5000)