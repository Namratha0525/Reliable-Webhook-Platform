from fastapi import FastAPI, Response
from pydantic import BaseModel

app = FastAPI(title="Demo Webhook Receiver")
unavailable = False
received = set()


class ReceiverMode(BaseModel):
    unavailable: bool


@app.put("/mode")
async def set_mode(mode: ReceiverMode):
    global unavailable
    unavailable = mode.unavailable
    return mode


@app.post("/receive")
async def receive(event: dict):
    if unavailable:
        return Response(status_code=503)
    received.add(event["id"])
    return Response(status_code=204)


@app.get("/received")
async def list_received():
    return {"event_ids": sorted(received)}
