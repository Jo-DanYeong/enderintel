"""
����Ŀ ��� ��� (���� ����)
TTS ����Ʈ�� ���� ���� ���� �ٷ� ����Ŀ�� ����մϴ�.
"""
import io
import sounddevice as sd
import soundfile as sf
import numpy as np
import tempfile
import os


def play_audio_bytes(audio_bytes: bytes):
    """
    mp3 ����Ʈ�� �޾� ����Ŀ�� �ٷ� ����մϴ�.
    ���� ���� ����.
    """
    tmp_path = None
    try:
        # soundfile�� mp3 ��Ʈ���� ���� �� �д� ��찡 �־ �ӽ����� ����
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        data, samplerate = sf.read(tmp_path, dtype="float32")
        sd.play(data, samplerate)
        sd.wait()

    except Exception as e:
        print(f"? ����� ��� ����: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def play_beep(frequency: int = 880, duration: float = 0.15):
    """����ũ���� ���� Ȯ�ο� ������."""
    try:
        samplerate = 44100
        t = np.linspace(0, duration, int(samplerate * duration), endpoint=False)
        wave = (0.3 * np.sin(2 * np.pi * frequency * t)).astype("float32")
        sd.play(wave, samplerate)
        sd.wait()
    except Exception as e:
        print(f"? ������ ����: {e}")