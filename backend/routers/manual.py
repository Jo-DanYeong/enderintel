"""
���� ���� �����
POST /api/manual/light - ���� ���� ����
POST /api/manual/cube  - ť�� ȸ�� ���� ����
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Literal

import esp32_client

router = APIRouter()


class LightRequest(BaseModel):
    action: Literal["ON", "OFF"]
    color: Literal["RED", "BLUE", "GREEN", "WHITE", "YELLOW", "PURPLE", "CYAN", "ORANGE"] = "WHITE"


class CubeRequest(BaseModel):
    action: Literal["SPIN_LEFT", "SPIN_RIGHT", "STOP"]


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