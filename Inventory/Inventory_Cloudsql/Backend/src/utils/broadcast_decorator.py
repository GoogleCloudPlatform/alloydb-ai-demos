from starlette.websockets import WebSocket, WebSocketDisconnect


# async def safe_send(websocket: WebSocket, message: str):
async def safe_send(broadcast_func, message: str):
    """
    Safely send a message to the WebSocket client.
    If the client disconnects, stop sending.
    """
    try:
        # await websocket.send_json({"status": message})
        await broadcast_func(message)
    except WebSocketDisconnect:
        print("⚠️ Client disconnected during broadcast")
        raise


def status_broadcast(label: str):
    """
    Decorator to send an initial status message before executing the function.
    Works per WebSocket connection.
    """

    def decorator(func):
        async def wrapper(websocket: WebSocket, *args, **kwargs):
            await safe_send(websocket, label)
            return await func(websocket, *args, **kwargs)

        return wrapper

    return decorator


# import functools
# import time
# import traceback

# def status_broadcast(label: str):
#     def decorator(func):
#         async def wrapper(broadcast, *args, **kwargs):
#             await broadcast(label)
#             return await func(broadcast, *args, **kwargs)
#         return wrapper
#     return decorator
