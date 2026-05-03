"""
����ũ���� ���� ��� (Vosk ���)
"���� ����" ��ȭ�� �ǽð����� �����մϴ�.
"""
import json
import queue
import threading
import sounddevice as sd
from vosk import Model, KaldiRecognizer


class WakeWordDetector:
    def __init__(self, model_path: str, wake_word: str = "���� ����",
                 samplerate: int = 16000, device_index: int = -1):
        self.wake_word = wake_word.lower().strip()
        self.samplerate = samplerate
        self.device = None if device_index == -1 else device_index
        self._audio_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._callback = None

        print(f"?? Vosk �� �ε� ��: {model_path}")
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, samplerate)
        print(f"? ����ũ���� ���� �غ� �Ϸ� (������: '{wake_word}')")

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f"??  ����� ����: {status}")
        self._audio_queue.put(bytes(indata))

    def _detection_loop(self):
        with sd.RawInputStream(
            samplerate=self.samplerate, channels=1, dtype="int16",
            device=self.device, blocksize=8000, callback=self._audio_callback,
        ):
            print(f"?? ����ũ���� ��� ��... ('{self.wake_word}'��� ���غ�����)")
            while not self._stop_event.is_set():
                try:
                    data = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "").lower().strip()
                    if text:
                        print(f"   [����] '{text}'")
                    if self._is_wake_word(text):
                        print(f"?? ����ũ���� ����!")
                        if self._callback:
                            self._callback()

    def _is_wake_word(self, text: str) -> bool:
        aliases = [self.wake_word, "���̿���", "hi ender", "���� ��", "������"]
        return any(alias in text for alias in aliases)

    def start(self, on_detected: callable):
        self._callback = on_detected
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if hasattr(self, "_thread"):
            self._thread.join(timeout=3)

    def pause(self):
        self._stop_event.set()

    def resume(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._thread.start()