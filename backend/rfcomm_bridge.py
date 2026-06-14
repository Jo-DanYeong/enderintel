"""Simple RFCOMM bridge to hold the connected ESP32 client socket and send commands.

This module is thread-safe and intended to be used by CommunicationSystem (which accepts
the RFCOMM connection) and by async API handlers which send commands via the bridge.
"""
import threading
from typing import Optional

_client_socket = None
_lock = threading.Lock()


def set_client_socket(sock) -> None:
    global _client_socket
    with _lock:
        _client_socket = sock


def clear_client_socket() -> None:
    global _client_socket
    with _lock:
        _client_socket = None


def get_client_socket():
    with _lock:
        return _client_socket


def send_command(command: str) -> dict:
    """Send a single command (string) over the RFCOMM socket.

    Returns a dict: {"success": bool, "message": str, "command": command}
    """
    sock = get_client_socket()
    if sock is None:
        return {"success": False, "message": "No RFCOMM client connected", "command": command}

    try:
        payload = (command.rstrip("\n") + "\n").encode("utf-8")
        with _lock:
            sock.sendall(payload)
        return {"success": True, "message": "sent", "command": command}
    except Exception as e:
        return {"success": False, "message": str(e), "command": command}
