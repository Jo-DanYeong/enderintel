import asyncio
import os
import threading
import httpx
from dotenv import load_dotenv

from recorder import record_voice, list_microphones
from audio_player import play_audio_bytes, play_beep
from wake_word import WakeWordDetector
from button_listener import ButtonListener

load_dotenv()

BACKEND_URL        = os.getenv("BACKEND_URL", "http://localhost:8000")
VOSK_MODEL_PATH    = os.getenv("VOSK_MODEL_PATH", "./vosk-model-small-ko-0.22")
WAKE_WORD          = os.getenv("WAKE_WORD", "엔더 활성화")
BUTTON_PIN         = int(os.getenv("BUTTON_PIN", "17"))
MIC_DEVICE_INDEX   = int(os.getenv("MIC_DEVICE_INDEX", "-1"))
MAX_RECORD_SECONDS = int(os.getenv("MAX_RECORD_SECONDS", "7"))


class EnderAssistant:
    def __init__(self):
        self._is_processing = False
        self.wake_detector = WakeWordDetector(
            model_path=VOSK_MODEL_PATH,
            wake_word=WAKE_WORD,
            device_index=MIC_DEVICE_INDEX,
        )
        self.button = ButtonListener(pin=BUTTON_PIN)

    def on_triggered(self):
        if self._is_processing:
            print("🔄 처리 중입니다. 잠시 후 다시 시도해주세요.")
            return
        threading.Thread(target=lambda: asyncio.run(self._pipeline()), daemon=True).start()

    async def _pipeline(self):
        self._is_processing = True
        wav_path = None
        try:
            self.wake_detector.pause()
            play_beep(frequency=880, duration=0.15)

            print("\n" + "="*40)
            print("🎤 녹음을 시작합니다!")
            print("="*40)

            wav_path = record_voice(
                max_seconds=MAX_RECORD_SECONDS,
                device_index=MIC_DEVICE_INDEX,
            )

            print("⚙️  AI 처리 중...")
            result = await self._send_to_backend(wav_path)

            if result:
                print(f"👤 사용자: {result.get('user_text', '')}")
                print(f"🤖 Ender:  {result.get('text_reply', '')}")

                audio_bytes = result.get("audio_bytes")
                if audio_bytes:
                    play_audio_bytes(audio_bytes)
            else:
                play_beep(frequency=440, duration=0.3)

        except Exception as e:
            print(f"❌ 처리 중 오류: {e}")
            play_beep(frequency=440, duration=0.3)
        finally:
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)
            self._is_processing = False
            self.wake_detector.resume()
            print("\n👂 다시 대기 중...\n")

    async def _send_to_backend(self, wav_path: str) -> dict | None:
        """
        wav 파일을 백엔드로 전송.
        백엔드가 TTS 오디오를 포함해서 반환.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(wav_path, "rb") as f:
                    response = await client.post(
                        f"{BACKEND_URL}/api/chat/audio",
                        files={"file": ("audio.wav", f, "audio/wav")},
                    )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            print(f"❌ 백엔드 연결 실패 ({BACKEND_URL})")
            return None
        except Exception as e:
            print(f"❌ 통신 오류: {e}")
            return None

    async def _send_text_to_backend(self, text: str) -> dict | None:
        """
        텍스트 입력을 백엔드로 전송 (개발/테스트용 대체 경로)
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{BACKEND_URL}/api/chat/text",
                    json={"text": text},
                )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            print(f"❌ 백엔드 연결 실패 ({BACKEND_URL})")
            return None
        except Exception as e:
            print(f"❌ 통신 오류: {e}")
            return None

    def run(self):
        print("\n" + "="*40)
        print("  🚀 Ender-Intel AI 시스템 시작")
        print(f"  백엔드: {BACKEND_URL}")
        print(f"  웨이크워드: '{WAKE_WORD}'")
        print("="*40 + "\n")

        # 웨이크워드/버튼이 사용 가능한 경우에만 시작
        wake_available = getattr(self.wake_detector, "_model_available", False)
        button_available = getattr(self.button, "_gpio_available", False)

        if wake_available:
            self.wake_detector.start(on_detected=self.on_triggered)
        else:
            print("!! 웨이크워드 비활성화: 마이크/모델이 없습니다.")

        if button_available:
            self.button.start(on_pressed=self.on_triggered)
        else:
            print("!! 버튼 비활성화: RPi.GPIO 사용 불가 또는 BUTTON_PIN=-1")

        # 둘 다 없으면 간단한 CLI 대체 모드 실행
        if not wake_available and not button_available:
            try:
                print("\n대체 CLI 모드: 텍스트를 입력하면 백엔드로 전송됩니다. 종료하려면 'quit' 입력")
                while True:
                    txt = input("> ").strip()
                    if not txt:
                        continue
                    if txt.lower() in ("quit", "exit"):
                        break
                    result = asyncio.run(self._send_text_to_backend(txt))
                    if result:
                        print(f"👤 사용자: {result.get('user_text', txt)}")
                        print(f"🤖 Ender:  {result.get('text_reply', '')}")
            except KeyboardInterrupt:
                pass
        else:
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                print("\n\n👋 Ender 시스템 종료")
        
        # 정리
        try:
            if wake_available:
                self.wake_detector.stop()
        except Exception:
            pass
        try:
            if button_available:
                self.button.stop()
        except Exception:
            pass


if __name__ == "__main__":
    list_microphones()
    EnderAssistant().run()