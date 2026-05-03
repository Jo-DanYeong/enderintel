"""
����ũ ���� ���
����ũ���� ���� �� ����� ������ �����ϰ� wav ���Ϸ� �����մϴ�.
"""
import sounddevice as sd
import soundfile as sf
import numpy as np
import tempfile


def record_voice(max_seconds: int = 7, samplerate: int = 16000,
                 device_index: int = -1) -> str:
    """
    ����ũ ���� �� �ӽ� wav ���� ��� ��ȯ.
    ������ 2�� �̻� ���ӵǸ� �ڵ� ����.
    """
    device = None if device_index == -1 else device_index
    silence_threshold = 0.01
    silence_limit = 2.0
    chunk_duration = 0.1
    chunk_samples = int(samplerate * chunk_duration)

    print(f"?? ���� ���� (�ִ� {max_seconds}��)")

    recorded_chunks = []
    silence_duration = 0.0
    total_duration = 0.0

    with sd.InputStream(samplerate=samplerate, channels=1, dtype="float32",
                        device=device, blocksize=chunk_samples) as stream:
        while total_duration < max_seconds:
            chunk, _ = stream.read(chunk_samples)
            recorded_chunks.append(chunk.copy())
            total_duration += chunk_duration

            rms = np.sqrt(np.mean(chunk**2))
            silence_duration = silence_duration + chunk_duration if rms < silence_threshold else 0.0

            if silence_duration >= silence_limit and total_duration > 1.0:
                print(f"?? ���� ���� - ���� ���� ({total_duration:.1f}��)")
                break

    print(f"? ���� �Ϸ� ({total_duration:.1f}��)")
    audio_data = np.concatenate(recorded_chunks, axis=0)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    sf.write(tmp.name, audio_data, samplerate)
    tmp.close()
    return tmp.name


def list_microphones():
    print("\n?? ��� ������ ����ũ:")
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            print(f"  [{i}] {dev['name']}")
    print()