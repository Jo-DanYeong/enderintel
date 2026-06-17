"""Bluetooth RFCOMM client connection manager for ESP32.

The ESP32 now exposes the BluetoothSerial server. The Raspberry Pi connects to
that server and the REST API writes plain text commands through rfcomm_bridge.
"""
import os
import socket
import threading
import time

from . import rfcomm_bridge

try:
    from bluetooth import BluetoothSocket, RFCOMM
    HAS_PYBLUEZ = True
except Exception:
    BluetoothSocket = None
    RFCOMM = None
    HAS_PYBLUEZ = False


DEFAULT_ESP32_ADDRESS = "44:1D:64:BE:03:1E"
DEFAULT_RFCOMM_CHANNEL = 1
DEFAULT_RETRY_SECONDS = 5.0

_stop_event = threading.Event()
_worker = None


def _create_rfcomm_socket():
    if HAS_PYBLUEZ:
        return BluetoothSocket(RFCOMM)

    return socket.socket(
        socket.AF_BLUETOOTH,
        socket.SOCK_STREAM,
        socket.BTPROTO_RFCOMM,
    )


def _connect_loop(address: str, channel: int, retry_seconds: float):
    while not _stop_event.is_set():
        if rfcomm_bridge.is_connected():
            time.sleep(1.0)
            continue

        sock = None
        try:
            print(f"[bluetooth] Connecting to ESP32 {address} channel {channel}...")
            sock = _create_rfcomm_socket()
            sock.connect((address, channel))
            rfcomm_bridge.set_client_socket(sock)
            print(f"[bluetooth] Connected to ESP32 {address} channel {channel}")

            while not _stop_event.is_set() and rfcomm_bridge.get_client_socket() is sock:
                time.sleep(1.0)

        except Exception as exc:
            print(f"[bluetooth] ESP32 connection failed: {exc}")
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            rfcomm_bridge.clear_client_socket(sock)
            time.sleep(retry_seconds)


def start_bluetooth_server(bind_address=None):
    """Start background ESP32 RFCOMM client loop.

    Name kept for compatibility with backend.main.
    """
    global _worker

    address = os.getenv("ESP32_BT_ADDRESS", DEFAULT_ESP32_ADDRESS)
    channel = int(os.getenv("ESP32_BT_CHANNEL", str(DEFAULT_RFCOMM_CHANNEL)))
    retry_seconds = float(os.getenv("ESP32_BT_RETRY_SECONDS", str(DEFAULT_RETRY_SECONDS)))

    _stop_event.clear()
    if _worker and _worker.is_alive():
        return {"thread": _worker, "server_socket": None}

    _worker = threading.Thread(
        target=_connect_loop,
        args=(address, channel, retry_seconds),
        daemon=True,
    )
    _worker.start()
    print("[bluetooth] ESP32 RFCOMM client thread started")
    return {"thread": _worker, "server_socket": None}


def stop_bluetooth_server(server_socket=None):
    """Stop background ESP32 RFCOMM client loop.

    Name kept for compatibility with backend.main.
    """
    _stop_event.set()
    sock = rfcomm_bridge.get_client_socket()
    rfcomm_bridge.clear_client_socket(sock)
    if sock is not None:
        try:
            sock.close()
        except Exception as exc:
            print(f"[bluetooth] Error closing ESP32 socket: {exc}")
