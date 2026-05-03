import os
import json
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv
 
import esp32_client
 
load_dotenv()
 
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TTS_VOICE = os.getenv("TTS_VOICE", "nova")
 
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "control_light",
            "description": "ť���� LED ������ �Ѱų� ���ϴ�. ����, ��, LED ���� ���ɿ� ȣ���ϼ���.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["ON", "OFF"],
                    },
                    "color": {
                        "type": "string",
                        "enum": ["RED", "BLUE", "GREEN", "WHITE", "YELLOW", "PURPLE", "CYAN", "ORANGE"],
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_cube",
            "description": "ť�긦 ȸ����Ű�ų� ������ŵ�ϴ�.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["SPIN_LEFT", "SPIN_RIGHT", "STOP"],
                    },
                },
                "required": ["action"],
            },
        },
    },
]
 
SYSTEM_PROMPT = """
You are a smart cube AI assistant named 'Ender-Intel', shaped like a Minecraft End Crystal. You can control the cube's LED lights and motors according to user commands. If hardware control is required, you must call the corresponding functions. For general questions, please answer kindly and concisely in Korean. Since the responses will be read via TTS, please speak in a natural, conversational tone.
"""

async def transcribe_audio(audio_path: str) -> str:
    suffix = Path(audio_path).suffix.lstrip(".")
    mime_map = {
        "m4a": "audio/mp4", "mp4": "audio/mp4",
        "mp3": "audio/mpeg", "wav": "audio/wav",
        "ogg": "audio/ogg", "webm": "audio/webm", "flac": "audio/flac",
    }
    mime = mime_map.get(suffix, "audio/mpeg")
    with open(audio_path, "rb") as f:
        result = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(f"audio.{suffix}", f, mime),
            language="ko",
        )
    return result.text

async def _execute_tool(name: str, args: dict) -> str:
    if name == "control_light":
        result = await esp32_client.send_led_command(
            args.get("action", "OFF"),
            args.get("color", "WHITE"),
        )
    elif name == "control_cube":
        result = await esp32_client.send_motor_command(args.get("action", "STOP"))
    else:
        result = {"success": False, "message": f"�� �� ���� �Լ�: {name}"}
    return json.dumps(result, ensure_ascii=False)
 
 
async def process_with_gpt(user_text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]
 
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )
    msg = response.choices[0].message
 
    if not msg.tool_calls:
        return msg.content or "�˼��ؿ�, �亯�� �������� ���߾��."
 
    messages.append(msg)
    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)
        print(f"?? {tc.function.name}({args})")
        result = await _execute_tool(tc.function.name, args)
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
 
    final = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    return final.choices[0].message.content or "������ ó���߾��."

async def text_to_speech_bytes(text: str) -> bytes:
    """���� ���� ���� mp3 ����Ʈ�� ��ȯ."""
    response = await client.audio.speech.create(
        model="tts-1",
        voice=TTS_VOICE,
        input=text,
    )
    return response.content
 
 
# ��������������������������������������������������������������������������������������������
# �� ���� - �ؽ�Ʈ in / �ؽ�Ʈ out
# ��������������������������������������������������������������������������������������������
async def handle_text_input(user_text: str) -> dict:
    """
    �� ��û ó��. ���� ���� ����.
    ESP32 ����� ���ο��� BLE�� ó��.
 
    Returns:
        {"user_text": str, "text_reply": str}
    """
    text_reply = await process_with_gpt(user_text)
    print(f"?? GPT: {text_reply}")
    return {"user_text": user_text, "text_reply": text_reply}
 
 
# ��������������������������������������������������������������������������������������������
# ���� ��ü - ����� in / TTS ����Ʈ out
# ��������������������������������������������������������������������������������������������
async def handle_audio_input(audio_path: str) -> dict:
    """
    ���� ����ũ �Է� ó��. ���� ���� ����.
    ����Ŀ ����� pi_local/main.py �� ���.
 
    Returns:
        {"user_text": str, "text_reply": str, "audio_bytes": bytes}
    """
    user_text = await transcribe_audio(audio_path)
    print(f"?? STT: {user_text}")
    text_reply = await process_with_gpt(user_text)
    print(f"?? GPT: {text_reply}")
    audio_bytes = await text_to_speech_bytes(text_reply)
    return {
        "user_text": user_text,
        "text_reply": text_reply,
        "audio_bytes": audio_bytes,
    }