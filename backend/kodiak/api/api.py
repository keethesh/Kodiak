from fastapi import APIRouter
from kodiak.api.endpoints import scans, ws, graph, approvals, projects

api_router = APIRouter()
api_router.include_router(scans.router, prefix="/scans", tags=["scans"])
api_router.include_router(ws.router, tags=["websocket"]) 
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
