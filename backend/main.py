import contextlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from kodiak.core.config import settings, validate_startup_config
from kodiak.database import init_db

# Global instances that need to be initialized during startup
event_manager = None
tool_inventory = None

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Kodiak Backend...")
    
    # Validate configuration
    try:
        validate_startup_config()
    except Exception as e:
        from kodiak.core.error_handling import ConfigurationError, ErrorHandler
        
        if isinstance(e, ConfigurationError):
            logger.critical(f"Configuration Error: {e.message}")
            if e.details:
                logger.critical(f"Details: {e.details}")
            ErrorHandler.log_error(e)
        else:
            logger.critical(f"Unexpected configuration error: {str(e)}")
            config_error = ConfigurationError(
                message=f"Unexpected configuration error: {str(e)}",
                details={"original_error": str(e), "error_type": type(e).__name__}
            )
            ErrorHandler.log_error(config_error)
        
        raise
    
    # Import models so SQLModel metadata is populated
    from kodiak.database import models  # noqa
    await init_db()
    
    # Initialize EventManager and ToolInventory
    await initialize_core_components()
    
    yield
    # Shutdown
    logger.info("Shutting down Kodiak Backend...")
    await shutdown_core_components()

async def initialize_core_components():
    """Initialize EventManager, ToolInventory, and other core components"""
    global event_manager, tool_inventory
    
    logger.info("Initializing core components...")
    
    # Initialize WebSocket manager and EventManager
    from kodiak.services.websocket_manager import manager as websocket_manager
    from kodiak.api.events import EventManager
    
    event_manager = EventManager(websocket_manager)
    logger.info("EventManager initialized")
    
    # Initialize ToolInventory with EventManager
    from kodiak.core.tools.inventory import ToolInventory
    tool_inventory = ToolInventory(event_manager)
    
    # Register all tools with EventManager
    tool_inventory.initialize_tools()
    logger.info(f"ToolInventory initialized with {len(tool_inventory.list_tools())} tools")
    
    # Initialize Hive Mind with EventManager
    from kodiak.core.hive_mind import hive_mind
    hive_mind.set_event_manager(event_manager)
    logger.info("Hive Mind configured with EventManager")
    
    # Store instances in app state for access by endpoints
    app.state.event_manager = event_manager
    app.state.tool_inventory = tool_inventory

async def shutdown_core_components():
    """Cleanup core components during shutdown"""
    global event_manager, tool_inventory
    
    logger.info("Shutting down core components...")
    
    # Clean up any resources if needed
    if tool_inventory:
        # Any cleanup needed for tools
        pass
    
    if event_manager:
        # Any cleanup needed for event manager
        pass

def get_event_manager():
    """Get the global EventManager instance"""
    return event_manager

def get_tool_inventory():
    """Get the global ToolInventory instance"""
    return tool_inventory

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "version": settings.VERSION}

from kodiak.api.api import api_router
app.include_router(api_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    import sys
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
