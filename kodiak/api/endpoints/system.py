"""
System status and integration endpoints.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from loguru import logger

router = APIRouter()


@router.get("/config-health")
async def get_configuration_health() -> Dict[str, Any]:
    """Get detailed configuration health status"""
    try:
        from kodiak.core.config import settings
        from kodiak.database.engine import verify_database_connectivity
        
        health_status = {
            "status": "healthy",
            "checks": {},
            "configuration": {},
            "issues": []
        }
        
        # Check LLM configuration
        try:
            llm_config = settings.get_llm_config()
            has_api_key = bool(llm_config.get("api_key"))
            
            health_status["checks"]["llm_provider"] = {
                "status": "healthy" if has_api_key else "unhealthy",
                "provider": settings.llm_provider,
                "model": settings.llm_model,
                "has_api_key": has_api_key,
                "display_name": settings.get_model_display_name()
            }
            
            if not has_api_key:
                health_status["issues"].append(f"Missing API key for LLM provider: {settings.llm_provider}")
                health_status["status"] = "unhealthy"
                
        except Exception as e:
            health_status["checks"]["llm_provider"] = {
                "status": "error",
                "error": str(e)
            }
            health_status["issues"].append(f"LLM configuration error: {str(e)}")
            health_status["status"] = "unhealthy"
        
        # Check database configuration
        try:
            await verify_database_connectivity()
            health_status["checks"]["database"] = {
                "status": "healthy",
                "server": settings.postgres_server,
                "port": settings.postgres_port,
                "database": settings.postgres_db,
                "user": settings.postgres_user
            }
        except Exception as e:
            health_status["checks"]["database"] = {
                "status": "unhealthy",
                "error": str(e),
                "server": settings.postgres_server,
                "port": settings.postgres_port,
                "database": settings.postgres_db
            }
            health_status["issues"].append(f"Database connectivity error: {str(e)}")
            health_status["status"] = "unhealthy"
        
        # Check required configuration values
        missing_config = settings.validate_required_config()
        if missing_config:
            health_status["checks"]["required_config"] = {
                "status": "unhealthy",
                "missing": missing_config
            }
            health_status["issues"].extend([f"Missing required config: {key}" for key in missing_config])
            health_status["status"] = "unhealthy"
        else:
            health_status["checks"]["required_config"] = {
                "status": "healthy",
                "all_present": True
            }
        
        # Add general configuration info
        health_status["configuration"] = {
            "debug_mode": settings.debug,
            "log_level": settings.log_level,
            "safety_checks": settings.enable_safety_checks,
            "max_agents": settings.max_concurrent_agents,
            "tool_timeout": settings.tool_timeout,
            "hive_mind_enabled": settings.enable_hive_mind
        }
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error checking configuration health: {e}")
        return {
            "status": "error",
            "error": str(e),
            "checks": {},
            "configuration": {},
            "issues": [f"Health check failed: {str(e)}"]
        }


@router.get("/config-troubleshooting")
async def get_configuration_troubleshooting() -> Dict[str, Any]:
    """Get configuration troubleshooting guide and diagnosis"""
    try:
        from kodiak.core.config import diagnose_configuration_issues
        
        diagnosis = diagnose_configuration_issues()
        
        return {
            "status": "success",
            "diagnosis": diagnosis
        }
        
    except Exception as e:
        logger.error(f"Error getting configuration troubleshooting: {e}")
        return {
            "status": "error",
            "error": str(e),
            "diagnosis": {
                "has_issues": True,
                "issues": [f"Troubleshooting failed: {str(e)}"],
                "solutions": ["Check system logs for more details"],
                "troubleshooting_guide": {}
            }
        }


@router.post("/validate-config")
async def validate_configuration() -> Dict[str, Any]:
    """Manually trigger configuration validation"""
    try:
        from kodiak.core.config import validate_startup_config
        
        # Run configuration validation
        validate_startup_config()
        
        return {
            "status": "success",
            "message": "Configuration validation passed",
            "timestamp": "now"
        }
        
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": "now"
        }


@router.get("/status")
async def get_system_status() -> Dict[str, Any]:
    """Get comprehensive system status including all integrations"""
    try:
        # Get core components
        from main import get_event_manager, get_tool_inventory
        from kodiak.core.hive_mind import hive_mind
        from kodiak.services.websocket_manager import manager as websocket_manager
        
        event_manager = get_event_manager()
        tool_inventory = get_tool_inventory()
        
        # Basic status
        status = {
            "status": "ok",
            "components": {
                "event_manager": {
                    "initialized": event_manager is not None,
                    "type": type(event_manager).__name__ if event_manager else None
                },
                "tool_inventory": {
                    "initialized": tool_inventory is not None,
                    "tools_count": len(tool_inventory.list_tools()) if tool_inventory else 0,
                    "tools": list(tool_inventory.list_tools().keys()) if tool_inventory else []
                },
                "hive_mind": {
                    "initialized": hive_mind is not None,
                    "stats": hive_mind.get_stats() if hive_mind else {}
                },
                "websocket_manager": {
                    "initialized": websocket_manager is not None,
                    "stats": websocket_manager.get_connection_stats() if websocket_manager else {}
                }
            }
        }
        
        # Check integration health
        integration_issues = []
        
        if not event_manager:
            integration_issues.append("EventManager not initialized")
        
        if not tool_inventory:
            integration_issues.append("ToolInventory not initialized")
        elif len(tool_inventory.list_tools()) == 0:
            integration_issues.append("No tools registered in ToolInventory")
        
        if not hive_mind:
            integration_issues.append("Hive Mind not initialized")
        
        status["integration_health"] = {
            "healthy": len(integration_issues) == 0,
            "issues": integration_issues
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting system status: {str(e)}")


@router.get("/integration-test")
async def test_integration() -> Dict[str, Any]:
    """Test the integration between EventManager, ToolInventory, and Hive Mind"""
    try:
        from kodiak.core.agent_factory import validate_dependencies, get_agent_dependencies
        
        # Validate dependencies
        validate_dependencies()
        
        event_manager, tool_inventory = get_agent_dependencies()
        
        # Test tool access
        tools = tool_inventory.list_tools()
        
        # Test getting a specific tool
        test_tool_name = list(tools.keys())[0] if tools else None
        test_tool = tool_inventory.get(test_tool_name) if test_tool_name else None
        
        # Test Hive Mind
        from kodiak.core.hive_mind import hive_mind
        hive_stats = hive_mind.get_stats()
        
        return {
            "status": "success",
            "tests": {
                "dependencies_valid": True,
                "event_manager_available": event_manager is not None,
                "tool_inventory_available": tool_inventory is not None,
                "tools_registered": len(tools),
                "sample_tool": {
                    "name": test_tool_name,
                    "available": test_tool is not None,
                    "has_event_manager": hasattr(test_tool, 'event_manager') and test_tool.event_manager is not None if test_tool else False
                },
                "hive_mind_stats": hive_stats
            }
        }
        
    except Exception as e:
        logger.error(f"Integration test failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "tests": {}
        }


@router.post("/create-test-agent")
async def create_test_agent() -> Dict[str, Any]:
    """Create a test agent to verify agent factory integration"""
    try:
        from kodiak.core.agent_factory import create_agent
        import uuid
        
        # Create a test agent
        agent_id = f"test_agent_{uuid.uuid4().hex[:8]}"
        agent = create_agent(
            agent_id=agent_id,
            role="generalist",
            project_id="test_project"
        )
        
        return {
            "status": "success",
            "agent": {
                "id": agent.agent_id,
                "role": agent.role,
                "available_tools": len(agent.available_tools),
                "has_event_manager": agent.event_manager is not None,
                "has_tool_inventory": agent.tool_inventory is not None
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to create test agent: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create test agent: {str(e)}")


@router.post("/test-error-handling")
async def test_error_handling() -> Dict[str, Any]:
    """Test comprehensive error handling across all integration points"""
    from kodiak.core.error_handling import (
        DatabaseError, WebSocketError, ConfigurationError, 
        ToolExecutionError, ErrorHandler, create_error_response
    )
    
    test_results = {
        "status": "success",
        "tests": {}
    }
    
    # Test database error handling
    try:
        db_error = DatabaseError(
            message="Test database connection failure",
            operation="test_connection",
            details={"test": True}
        )
        ErrorHandler.log_error(db_error)
        test_results["tests"]["database_error"] = {
            "passed": True,
            "error_dict": db_error.to_dict()
        }
    except Exception as e:
        test_results["tests"]["database_error"] = {
            "passed": False,
            "error": str(e)
        }
    
    # Test WebSocket error handling
    try:
        ws_error = WebSocketError(
            message="Test WebSocket disconnection",
            client_id="test_client",
            details={"test": True}
        )
        ErrorHandler.log_error(ws_error)
        test_results["tests"]["websocket_error"] = {
            "passed": True,
            "error_dict": ws_error.to_dict()
        }
    except Exception as e:
        test_results["tests"]["websocket_error"] = {
            "passed": False,
            "error": str(e)
        }
    
    # Test configuration error handling
    try:
        config_error = ConfigurationError(
            message="Test configuration validation failure",
            config_key="test_key",
            details={"test": True}
        )
        ErrorHandler.log_error(config_error)
        test_results["tests"]["configuration_error"] = {
            "passed": True,
            "error_dict": config_error.to_dict()
        }
    except Exception as e:
        test_results["tests"]["configuration_error"] = {
            "passed": False,
            "error": str(e)
        }
    
    # Test error response creation
    try:
        error_response = create_error_response(
            ToolExecutionError("Test tool execution failure", tool_name="test_tool")
        )
        test_results["tests"]["error_response"] = {
            "passed": True,
            "response": error_response
        }
    except Exception as e:
        test_results["tests"]["error_response"] = {
            "passed": False,
            "error": str(e)
        }
    
    # Test EventManager error handling
    try:
        from main import get_event_manager
        event_manager = get_event_manager()
        
        if event_manager:
            health_status = event_manager.get_health_status()
            test_results["tests"]["event_manager_health"] = {
                "passed": True,
                "health_status": health_status
            }
        else:
            test_results["tests"]["event_manager_health"] = {
                "passed": False,
                "error": "EventManager not initialized"
            }
    except Exception as e:
        test_results["tests"]["event_manager_health"] = {
            "passed": False,
            "error": str(e)
        }
    
    # Calculate overall success
    passed_tests = sum(1 for test in test_results["tests"].values() if test.get("passed", False))
    total_tests = len(test_results["tests"])
    
    test_results["summary"] = {
        "passed": passed_tests,
        "total": total_tests,
        "success_rate": passed_tests / total_tests if total_tests > 0 else 0
    }
    
    return test_results