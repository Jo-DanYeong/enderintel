import threading
import asyncio
import time
import os
import socket

try:
    # Prefer pybluez: provides BluetoothSocket and RFCOMM for RFCOMM server sockets
    from bluetooth import BluetoothSocket, RFCOMM  # pybluez
    try:
        # pybluez extras
        from bluetooth import advertise_service, SERIAL_PORT_CLASS, SERIAL_PORT_PROFILE
        HAS_PYBLUEZ_SDP = True
    except Exception:
        advertise_service = None
        SERIAL_PORT_CLASS = None
        SERIAL_PORT_PROFILE = None
        HAS_PYBLUEZ_SDP = False
    # rudimentary check that this is pybluez-like
    HAS_PYBLUEZ = hasattr(RFCOMM, "__class__") or BluetoothSocket is not None
except Exception:
    BluetoothSocket = None
    RFCOMM = None
    HAS_PYBLUEZ = False
    HAS_PYBLUEZ_SDP = False

try:
    from CommunicationSystem import CommunicationSys
    HAS_COMM_SYS = True
except Exception:
    CommunicationSys = None
    HAS_COMM_SYS = False

from . import ai_handler


def _ai_trigger_wrapper():
    """Synchronous wrapper to call async ai_handler.handle_text_input from a thread.

    Returns the text reply string (or an error message).
    """
    try:
        result = asyncio.run(ai_handler.handle_text_input("ender"))
        return result.get("text_reply", "") if isinstance(result, dict) else str(result)
    except Exception as e:
        return f"AI trigger failed: {e}"


def start_bluetooth_server(bind_address=None):
    """Start the RFCOMM Bluetooth server in a background thread.

    Returns a dict with keys: thread, server_socket
    """
    if not HAS_COMM_SYS:
        print("[bluetooth] CommunicationSystem module not found; skipping Bluetooth server start.")
        return {"thread": None, "server_socket": None}

    # Default to the previously used adapter MAC if not provided; can be overridden with BT_BIND_ADDRESS env
    if bind_address is None:
        bind_address = os.getenv("BT_BIND_ADDRESS", "E4:5F:01:7B:E6:3D")

    server_sock = None

    # Try pybluez BluetoothSocket first
    if HAS_PYBLUEZ:
        try:
            server_sock = BluetoothSocket(RFCOMM)
            print("[bluetooth] Using pybluez BluetoothSocket")
        except Exception as e:
            print(f"[bluetooth] pybluez BluetoothSocket creation failed: {e}")

    # Fallback: try native AF_BLUETOOTH RFCOMM socket (Linux)
    if server_sock is None:
        try:
            server_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            print("[bluetooth] Using native AF_BLUETOOTH socket as fallback")
        except Exception as e:
            print(f"[bluetooth] No Bluetooth socket available (pybluez missing and native socket failed): {e}")
            return {"thread": None, "server_socket": None}

    # Do not bind here; CommunicationSystem will bind using BT_BIND_ADDRESS.
    print(f"[bluetooth] Created RFCOMM socket, will bind in CommunicationSystem to {bind_address}:1")

    # If pybluez is available and SDP functions exist, advertise an SPP service so ESP32 can discover/connect
    if HAS_PYBLUEZ and HAS_PYBLUEZ_SDP and advertise_service and SERIAL_PORT_CLASS:
        try:
            service_name = os.getenv("BT_SERVICE_NAME", "Ender-SPP")
            service_uuid = os.getenv("BT_SERVICE_UUID", "00001101-0000-1000-8000-00805F9B34FB")
            advertise_service(server_sock,
                              service_name,
                              service_id=service_uuid,
                              service_classes=[service_uuid, SERIAL_PORT_CLASS],
                              profiles=[SERIAL_PORT_PROFILE])
            print(f"[bluetooth] Advertised SPP service '{service_name}' (UUID={service_uuid}) via SDP")
        except Exception as e:
            print(f"[bluetooth] Failed to advertise SPP service via pybluez: {e}")

    comm = CommunicationSys(server_sock, ai_trigger_callback=_ai_trigger_wrapper)

    def _run():
        try:
            comm.CommSys()
        except Exception as e:
            print(f"[bluetooth] CommunicationSys exited with error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    # give it a moment to initialize
    time.sleep(0.2)
    print("[bluetooth] Bluetooth server thread started")
    return {"thread": t, "server_socket": server_sock}


def stop_bluetooth_server(server_socket):
    try:
        if server_socket:
            server_socket.close()
            print("[bluetooth] Server socket closed")
    except Exception as e:
        print(f"[bluetooth] Error closing server socket: {e}")
