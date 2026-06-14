"""
GPIO ��ư ������
ť�� ��ħ�뿡 �޸� ���� ��ư �Է��� �����մϴ�.
GPIO ���� ȯ��(PC ��)������ �ڵ����� ��Ȱ��ȭ�˴ϴ�.
"""
import threading


class ButtonListener:
    def __init__(self, pin: int = 17):
        self.pin = pin
        self._gpio_available = False

        if pin == -1:
            print("??  ��ư ��Ȱ��ȭ (BUTTON_PIN=-1)")
            return

        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._gpio_available = True
            print(f"? GPIO ��ư �ʱ�ȭ �Ϸ� (BCM ��: {pin})")
        except (ImportError, RuntimeError):
            print("??  RPi.GPIO ���� - ��ư ��� ��Ȱ��ȭ")

    def start(self, on_pressed: callable):
        self._callback = on_pressed
        if not self._gpio_available:
            return
        try:
            self.GPIO.add_event_detect(
                self.pin, self.GPIO.FALLING,
                callback=lambda _: threading.Thread(
                    target=self._callback, daemon=True
                ).start(),
                bouncetime=300,
            )
            print(f"?? ??ư ????? ?? (BCM {self.pin})")
        except RuntimeError as e:
            print(f"??  ??ư ??? ??? (GPIO ???? ??? ?): {e}")
            self._gpio_available = False

    def stop(self):
        if self._gpio_available:
            self.GPIO.remove_event_detect(self.pin)
            self.GPIO.cleanup()