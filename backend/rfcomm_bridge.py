"""Thread-safe RFCOMM bridge for ESP32 command and state exchange."""
import os
import socket
import threading
import time
from typing import Any

_client_socket = None
_lock = threading.Lock()

DEFAULT_STATE_TIMEOUT = float(os.getenv("ESP32_STATE_TIMEOUT", "1.0"))
MAX_STATE_RESPONSE_BYTES = 16 * 1024


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


def _parse_scalar(value: str) -> Any:
    """Convert a protocol value to bool/int/float when possible."""
    if value in ("0", "1"):
        return value == "1"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def parse_state_line(line: str) -> dict:
    """Parse the ESP32 ``STATE key=value ...`` response."""
    line = line.strip()
    if line != "STATE" and not line.startswith("STATE "):
        raise ValueError("Not an ESP32 STATE response")

    state = {}
    for token in line[5:].strip().split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key == "led":
            components = value.split(",")
            if len(components) != 3:
                raise ValueError("Invalid LED value in STATE response")
            state[key] = [int(component) for component in components]
        else:
            state[key] = _parse_scalar(value)

    return state


def request_state(timeout: float = DEFAULT_STATE_TIMEOUT) -> dict:
    """Request and parse the live state from the connected ESP32.

    A socket object by itself is not proof that the ESP32 is still powered on.
    The connection is considered alive only after a complete ``STATE`` line is
    received. Any timeout, closed connection, or malformed response clears and
    closes the stale socket.
    """
    global _client_socket

    sock = None
    previous_timeout = None
    response_line = None
    error = None

    # Keep command sending and response reading atomic. Otherwise another API
    # command could be written while APPSTATE's response is being collected.
    with _lock:
        sock = _client_socket
        if sock is None:
            return {"success": False, "message": "No RFCOMM client connected"}

        try:
            if hasattr(sock, "gettimeout"):
                previous_timeout = sock.gettimeout()

            deadline = time.monotonic() + timeout
            sock.settimeout(timeout)
            sock.sendall(b"APPSTATE\n")

            buffer = bytearray()
            while response_line is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for ESP32 STATE response")

                sock.settimeout(remaining)
                chunk = sock.recv(1024)
                if not chunk:
                    raise ConnectionError("ESP32 closed the RFCOMM connection")

                buffer.extend(chunk)
                if len(buffer) > MAX_STATE_RESPONSE_BYTES:
                    raise ValueError("ESP32 STATE response is too large")

                while b"\n" in buffer:
                    raw_line, _, remainder = buffer.partition(b"\n")
                    buffer = bytearray(remainder)
                    candidate = raw_line.decode("utf-8", errors="replace").strip("\r ")
                    if candidate == "STATE" or candidate.startswith("STATE "):
                        response_line = candidate
                        break

            state = parse_state_line(response_line)
        except (socket.timeout, TimeoutError) as exc:
            error = f"Timed out waiting for ESP32 STATE response: {exc}"
        except Exception as exc:
            error = str(exc)
        finally:
            if error is None:
                try:
                    sock.settimeout(previous_timeout)
                except Exception:
                    pass
            elif sock is _client_socket:
                _client_socket = None

    if error is not None:
        try:
            sock.close()
        except Exception:
            pass
        return {"success": False, "message": error}

    return {
        "success": True,
        "message": "ESP32 STATE response received",
        "raw": response_line,
        "state": state,
    }
