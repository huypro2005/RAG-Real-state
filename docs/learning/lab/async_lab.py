from fastapi import FastAPI, APIRouter
from threading import Thread, current_thread
import time

app = FastAPI()

router = APIRouter()

@router.get("/block")
async def block_endpoint():
    time.sleep(3)  # Simulate a blocking operation
    return {"message": "This endpoint running on thread block " + current_thread().name + " blocks for 3 seconds."}


@router.get("/nonblock")
async def nonblock_endpoint():
    import asyncio
    await asyncio.sleep(3)  # Simulate a non-blocking operation
    return {"message": "This endpoint running on thread nonblock " + current_thread().name + " does not block for 3 seconds."}

@router.get("/thread")
def thread_endpoint():
    time.sleep(3)  # Simulate a blocking operation
    return {"message": "This endpoint running on thread thread " + current_thread().name + " blocks for 3 seconds."}


app.include_router(router, tags=["lab"])