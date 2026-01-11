from fastapi import APIRouter
from kodiak.api.endpoints import scans, ws

api_router = APIRouter()
api_router.include_router(scans.router, prefix="/scans", tags=["scans"])
api_router.include_router(ws.router, tags=["websocket"]) # WS usually doesn't have a prefix if it's at root/ws, or keep structure
# api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
