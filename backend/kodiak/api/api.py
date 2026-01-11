from fastapi import APIRouter
from kodiak.api.endpoints import scans

api_router = APIRouter()
api_router.include_router(scans.router, prefix="/scans", tags=["scans"])
# api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
