"""Thread-safe RFCOMM bridge for ESP32 command sending."""
import threading

_client_socket = None
_lock = threading.Lock()


def set_client_socket(sock) -> None:
    global _client_socket
    with _lock:
        _client_socket = sock


def clear_client_socket(sock=None) -> None:
    global _client_socket
    with _lock:
        if sock is None or sock is _client_socket:
            _client_socket = None


def get_client_socket():
    with _lock:
        return _client_socket


def is_connected() -> bool:
    return get_client_socket() is not None


def send_command(command: str) -> dict:
    """Send a single command (string) over the RFCOMM socket.

    Returns a dict: {"success": bool, "message": str, "command": command}
    """
    with _lock:
        sock = _client_socket
    if sock is None:
        return {"success": False, "message": "No RFCOMM client connected", "command": command}

    try:
        payload = (command.rstrip("\n") + "\n").encode("utf-8")
        with _lock:
            sock.sendall(payload)
        return {"success": True, "message": "sent", "command": command}
    except Exception as e:
        clear_client_socket(sock)
        return {"success": False, "message": str(e), "command": command}
