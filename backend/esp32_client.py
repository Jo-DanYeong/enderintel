"""RFCOMM-based ESP32 command sender.

This module sends plain text commands over the RFCOMM socket registered in
`backend.rfcomm_bridge`. It preserves the async function names used elsewhere.
"""
import asyncio
import os
from typing import Any

from . import rfcomm_bridge


COLOR_MAP = {
    "RED": (255, 0, 0),
    "GREEN": (0, 255, 0),
    "BLUE": (0, 0, 255),
    "WHITE": (255, 255, 255),
    "YELLOW": (255, 255, 0),
    "PURPLE": (128, 0, 128),
    "CYAN": (0, 255, 255),
    "ORANGE": (255, 140, 0),
}


def _normalize_color(color: Any):
    """Return (r,g,b) tuple or raise ValueError."""
    if isinstance(color, dict):
        r = int(color.get("r", 0))
        g = int(color.get("g", 0))
        b = int(color.get("b", 0))
    elif isinstance(color, str):
        s = color.strip()
        if s.startswith("#") and len(s) == 7:
            r = int(s[1:3], 16)
            g = int(s[3:5], 16)
            b = int(s[5:7], 16)
        elif len(s) == 6 and all(c in "0123456789ABCDEFabcdef" for c in s):
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
        else:
            named = COLOR_MAP.get(s.upper())
            if not named:
                raise ValueError(f"Unknown color: {color}")
            return named
    elif isinstance(color, tuple) and len(color) == 3:
        r, g, b = color
    else:
        raise ValueError("Unsupported color type")

    for v in (r, g, b):
        if v < 0 or v > 255:
            raise ValueError("RGB components must be 0-255")
    return (int(r), int(g), int(b))


async def send_led_command(state: str, color: Any = "WHITE") -> dict:
    """Send LED command via RFCOMM bridge.

    Returns dict with success/message/command.
    """
    try:
        if state.upper() != "ON":
            r, g, b = (0, 0, 0)
        else:
            r, g, b = _normalize_color(color)

        cmd = f"LED {r} {g} {b}"

        # send in thread to avoid blocking
        result = await asyncio.to_thread(rfcomm_bridge.send_command, cmd)
        return {"success": result.get("success", False), "message": result.get("message", ""), "command": cmd}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def send_motor_command(command: str) -> dict:
    """Translate a logical motor command to RFCOMM text commands.

    Accepts commands like 'SPIN_LEFT', 'SPIN_RIGHT', 'STOP', or raw instructions.
    """
    cmd = (command or "").upper()
    commands = []
    if cmd == "SPIN_LEFT":
        commands = ["AUTO 0", "M Y 85"]
    elif cmd == "SPIN_RIGHT":
        commands = ["AUTO 0", "M Y 95"]
    elif cmd == "STOP":
        commands = ["AUTO 0", "M 90"]
    else:
        # If user provided a direct motor command like 'M 90' or 'M Y 100', send it safely
        # Validate simple patterns
        parts = cmd.split()
        if parts and parts[0] in ("M", "AUTO", "M","TARGET","PID","DIR","ZERO"):
            # single-line passthrough
            commands = [cmd]
        else:
            return {"success": False, "message": f"Unknown motor action: {command}"}

    results = []
    for c in commands:
        res = await asyncio.to_thread(rfcomm_bridge.send_command, c)
        results.append(res)
        if not res.get("success"):
            return {"success": False, "message": f"Failed to send: {c}", "details": res}

    return {"success": True, "message": "sent", "commands": commands}