"""
웨이크워드 감지기 (Vosk 사용)
모델이 없거나 생성 실패 시 안전하게 비활성화됩니다.
"""
import json
import os
import queue
import threading
import sounddevice as sd
from vosk import Model, KaldiRecognizer


class WakeWordDetector:
    def __init__(self, model_path: str, wake_word: str = "엔더 활성화",
                 samplerate: int = 16000, device_index: int = -1):
        self.wake_word = wake_word.lower().strip()
        self.samplerate = samplerate
        self.device = None if device_index == -1 else device_index
        self._audio_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._callback = None

        print(f"?? Vosk 모델 경로: {model_path}")

        # 모델 유효성 검사
        self._model_available = False
        if not os.path.isdir(model_path):
            print(f"!! Vosk 모델 폴더가 없습니다: {model_path}\n   (경로를 확인하거나 모델을 다운로드하세요)")
            self.model = None
            self.recognizer = None
            return

        try:
            self.model = Model(model_path)
            self.recognizer = KaldiRecognizer(self.model, samplerate)
            self._model_available = True
            print(f"? Vosk 모델 로드 완료 (웨이크워드: '{wake_word}')")
        except Exception as e:
            print(f"!! Vosk 모델 생성 실패: {e}\n   모델이 손상되었거나 포맷이 잘못되었을 수 있습니다.")
            self.model = None
            self.recognizer = None
            self._model_available = False

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f"!! 오디오 상태 경고: {status}")
        self._audio_queue.put(bytes(indata))

    def _detection_loop(self):
        if not self._model_available:
            print("!! 웨이크워드 감지 비활성화: 모델이 없습니다.")
            return

        try:
            stream = sd.RawInputStream(
                samplerate=self.samplerate, channels=1, dtype="int16",
                device=self.device, blocksize=8000, callback=self._audio_callback,
            )
        except Exception as e:
            print(f"!! 오디오 입력 스트림 생성 실패: {e}")
            try:
                print("!! 사용 가능한 입력 장치 목록:")
                for i, dev in enumerate(sd.query_devices()):
                    if dev.get("max_input_channels", 0) > 0:
                        print(f"  [{i}] {dev['name']}")
            except Exception:
                print("!! 입력 장치 정보를 가져올 수 없습니다.")
            return

        with stream:
            print(f"?? 웨이크워드 감지 시작... ('{self.wake_word}' 말하기)")
            while not self._stop_event.is_set():
                try:
                    data = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "").lower().strip()
                    if text:
                        print(f"   [인식] '{text}'")
                    if self._is_wake_word(text):
                        print(f"?? 웨이크워드 검출!")
                        if self._callback:
                            try:
                                self._callback()
                            except Exception as e:
                                print(f"!! 콜백 실행 중 오류: {e}")

    def _is_wake_word(self, text: str) -> bool:
        aliases = [self.wake_word, "하이 엔더", "hi ender", "안녕 엔더", "엔더야"]
        return any(alias in text for alias in aliases)

    def start(self, on_detected: callable):
        self._callback = on_detected
        if not self._model_available:
            print("!! 웨이크워드 비활성화 상태: start()를 무시합니다.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._thread.start()

    def stop(self):
        if not self._model_available:
            return
        self._stop_event.set()
        if hasattr(self, "_thread"):
            self._thread.join(timeout=3)

    def pause(self):
        if not self._model_available:
            return
        self._stop_event.set()

    def resume(self):
        if not self._model_available:
            print("!! 웨이크워드 비활성화 상태: resume()를 무시합니다.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._thread.start()