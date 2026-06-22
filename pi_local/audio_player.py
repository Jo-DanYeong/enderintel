import base64
import os
import tempfile
import subprocess

def play_audio_bytes(audio_base64: str):
    """
    �鿣�忡�� ���� Base64 ���� �����͸� 
    ���� �����(3.5mm ����� ��)�� ���� ����մϴ�.
    """
    if not audio_base64:
        print("[-] ����� ����� �����Ͱ� �����ϴ�.")
        return

    try:
        # 1. Base64 ���ڵ��Ͽ� ���̳ʸ� ���̺� �����ͷ� ��ȯ
        audio_bytes = base64.b64decode(audio_base64)
        
        # 2. �ӽ� WAV ���� ����
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            temp_filename = tmp_file.name

        print(f"[+] �ӽ� ����� ���� ���� �Ϸ�: {temp_filename}")
        print("[??] ����ٷ� ���� ����� �õ��մϴ�...")

        # 3. ����� ���� ���� ����� ��(ALSA ����̹�)���� ��� ���� ����
        # -q�� �α� ���� �ɼ��Դϴ�.
        result = subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", temp_filename],
            check=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("[+] ����Ŀ ��� ����!")
        else:
            print(f"[-] aplay ��� ���� (�����ڵ�: {result.returncode})")

    except Exception as e:
        print(f"[-] ����Ŀ ��� �� ġ���� ���� �߻�: {e}")
        
    finally:
        # ����� ������ �ӽ� ������ ����ϰ� ����
        if 'temp_filename' in locals() and os.path.exists(temp_filename):
            os.remove(temp_filename)


def play_beep(frequency=880, duration=0.15):
    """
    �ý��� ��ü �������� ���� ��� (�ʿ�� ���, ����� ������ �α׸� ���)
    """
    print(f"[Beep] {frequency}Hz�� {duration}�� ���� �˸��� �߻�")