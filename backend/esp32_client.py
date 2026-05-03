"""
ESP32 BLE Ŭ���̾�Ʈ
���� �� BLE �� ESP32 ���� ����
"""
import asyncio
import json
import os
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from dotenv import load_dotenv

load_dotenv()

ESP32_DEVICE_NAME = os.getenv("ESP32_DEVICE_NAME", "Ender-Intel")
CHAR_LED_UUID     = "12345678-1234-1234-1234-123456789001"
CHAR_MOTOR_UUID   = "12345678-1234-1234-1234-123456789002"

MAX_RETRIES  = 3
RETRY_DELAY  = 1.0
SCAN_TIMEOUT = 5.0

COLOR_MAP: dict[str, str] = {
    "RED":    "#FF0000",
    "GREEN":  "#00FF00",
    "BLUE":   "#0000FF",
    "WHITE":  "#FFFFFF",
    "YELLOW": "#FFFF00",
    "PURPLE": "#800080",
    "CYAN":   "#00FFFF",
    "ORANGE": "#FF8C00",
}


async def _find_esp32() -> str | None:
    print(f"?? BLE ��ĵ ��... ({ESP32_DEVICE_NAME})")
    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT)
    for d in devices:
        if d.name and ESP32_DEVICE_NAME in d.name:
            print(f"? �߰�: {d.name} ({d.address})")
            return d.address
    print("? ESP32�� ã�� ���߽��ϴ�.")
    return None


async def _send_ble_command(char_uuid: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            address = await _find_esp32()
            if not address:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                return {"success": False, "message": "ESP32�� ã�� �� �����ϴ�."}

            async with BleakClient(address, timeout=10.0) as client:
                await client.write_gatt_char(char_uuid, data, response=False)
                print(f"? BLE ���� ����: {payload}")
                return {"success": True, "message": f"���� ����: {payload}"}

        except BleakError as e:
            print(f"??  BLE ���� ({attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
        except Exception as e:
            return {"success": False, "message": str(e)}

    return {"success": False, "message": f"{MAX_RETRIES}ȸ �õ� �� ����"}


async def send_led_command(state: str, color: str = "WHITE") -> dict:
    hex_color = COLOR_MAP.get(color.upper(), "#FFFFFF") if state == "ON" else "#000000"
    return await _send_ble_command(CHAR_LED_UUID, {"state": state, "color": hex_color})


async def send_motor_command(command: str) -> dict:
    return await _send_ble_command(CHAR_MOTOR_UUID, {"command": command.upper()})