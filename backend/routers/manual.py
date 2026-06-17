"""
���� ���� �����
POST /api/manual/light - ���� ���� ����
POST /api/manual/cube  - ť�� ȸ�� ���� ����
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Literal
from typing import Any

from .. import esp32_client
from .. import rfcomm_bridge
import asyncio

router = APIRouter()


class LightRequest(BaseModel):
    action: Literal["ON", "OFF"]
    # Accept named colors, hex string '#RRGGBB' or 'RRGGBB', or an RGB dict {r,g,b}
    color: Any = "WHITE"


class CubeRequest(BaseModel):
    action: Literal["SPIN_LEFT", "SPIN_RIGHT", "STOP"]


@router.get("/connection", summary="ESP32 Bluetooth connection state")
async def manual_connection():
    return JSONResponse(content={"connected": rfcomm_bridge.is_connected()})


@router.post("/light", summary="���� ���� ����")
async def manual_light(body: LightRequest):
    result = await esp32_client.send_led_command(body.action, body.color)
    if not result["success"]:
        raise HTTPException(status_code=503, detail=result["message"])
    return JSONResponse(content=result)


@router.post("/cube", summary="ť�� ���� ����")
async def manual_cube(body: CubeRequest):
    result = await esp32_client.send_motor_command(body.action)
    if not result["success"]:
        raise HTTPException(status_code=503, detail=result["message"])
    return JSONResponse(content=result)


@router.post("/zero", summary="제로(현재 각도를 기준으로 0으로 설정)")
async def manual_zero():
    """Set current angles as zero reference on the ESP32."""
    # send via rfcomm_bridge in thread to avoid blocking event loop
    res = await asyncio.to_thread(rfcomm_bridge.send_command, "ZERO")
    if not res.get("success"):
        raise HTTPException(status_code=503, detail=res.get("message", "failed to send"))
    return JSONResponse(content=res)


@router.post("/balance/on", summary="Enable balancing (BALANCE ON)")
async def manual_balance_on():
    res = await asyncio.to_thread(rfcomm_bridge.send_command, "BALANCE ON")
    if not res.get("success"):
        raise HTTPException(status_code=503, detail=res.get("message", "failed to send"))
    return JSONResponse(content=res)


@router.post("/balance/off", summary="Disable balancing (BALANCE OFF)")
async def manual_balance_off():
    # BALANCE OFF should immediately stop balancing and set motors neutral on ESP32
    res = await asyncio.to_thread(rfcomm_bridge.send_command, "BALANCE OFF")
    if not res.get("success"):
        raise HTTPException(status_code=503, detail=res.get("message", "failed to send"))
    return JSONResponse(content=res)
