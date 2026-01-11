"""
Comprehensive error handling for Kodiak integration points.

This module provides centralized error handling, logging, and recovery
mechanisms for all system components.
"""

import traceback
from typing import Any, Dict, Optional, Union, Callable
from enum import Enum
from loguru import logger
from functools import wraps


class ErrorSeverity(str, Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Error categories for better classification"""
    DATABASE = "database"
    WEBSOCKET = "websocket"
    CONFIGURATION = "configuration"
    TOOL_EXECUTION = "tool_execution"
    AGENT_COORDINATION = "agent_coordination"
    HIVE_MIND = "hive_mind"
    EVENT_BROADCASTING = "event_broadcasting"


class KodiakError(Exception):
    """Base exception class for Kodiak-specific errors"""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = True
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.recoverable = recoverable
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/API responses"""
        return {
            "error": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "details": self.details,
            "recoverable": self.recoverable,
            "type": self.__class__.__name__
        }


class DatabaseError(KodiakError):
    """Database operation errors"""
    
    def __init__(self, message: str, operation: str = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.DATABASE,
            **kwargs
        )
        if operation:
            self.details["operation"] = operation


class WebSocketError(KodiakError):
    """WebSocket connection and communication errors"""
    
    def __init__(self, message: str, client_id: str = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.WEBSOCKET,
            **kwargs
        )
        if client_id:
            self.details["client_id"] = client_id


class ConfigurationError(KodiakError):
    """Configuration validation and loading errors"""
    
    def __init__(self, message: str, config_key: str = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.HIGH,
            recoverable=False,
            **kwargs
        )
        if config_key:
            self.details["config_key"] = config_key


class ToolExecutionError(KodiakError):
    """Tool execution errors"""
    
    def __init__(self, message: str, tool_name: str = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.TOOL_EXECUTION,
            **kwargs
        )
        if tool_name:
            self.details["tool_name"] = tool_name


class AgentCoordinationError(KodiakError):
    """Agent coordination and communication errors"""
    
    def __init__(self, message: str, agent_id: str = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.AGENT_COORDINATION,
            **kwargs
        )
        if agent_id:
            self.details["agent_id"] = agent_id


class HiveMindError(KodiakError):
    """Hive Mind synchronization errors"""
    
    def __init__(self, message: str, command: str = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.HIVE_MIND,
            **kwargs
        )
        if command:
            self.details["command"] = command


class EventBroadcastingError(KodiakError):
    """Event broadcasting and WebSocket errors"""
    
    def __init__(self, message: str, event_type: str = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.EVENT_BROADCASTING,
            **kwargs
        )
        if event_type:
            self.details["event_type"] = event_type


class ErrorHandler:
    """Centralized error handling and recovery"""
    
    @staticmethod
    def log_error(error: Union[Exception, KodiakError], context: Dict[str, Any] = None):
        """Log an error with appropriate level and context"""
        context = context or {}
        
        if isinstance(error, KodiakError):
            log_data = {
                **error.to_dict(),
                **context
            }
            
            # Log based on severity
            if error.severity == ErrorSeverity.CRITICAL:
                logger.critical(f"CRITICAL ERROR: {error.message}", extra=log_data)
            elif error.severity == ErrorSeverity.HIGH:
                logger.error(f"HIGH SEVERITY: {error.message}", extra=log_data)
            elif error.severity == ErrorSeverity.MEDIUM:
                logger.warning(f"MEDIUM SEVERITY: {error.message}", extra=log_data)
            else:
                logger.info(f"LOW SEVERITY: {error.message}", extra=log_data)
        else:
            # Standard exception
            logger.error(f"Unhandled exception: {str(error)}", extra={
                "exception_type": type(error).__name__,
                "traceback": traceback.format_exc(),
                **context
            })
    
    @staticmethod
    def handle_database_error(
        operation: str,
        error: Exception,
        context: Dict[str, Any] = None
    ) -> DatabaseError:
        """Handle database operation errors"""
        context = context or {}
        
        # Create descriptive error message
        if "connection" in str(error).lower():
            message = f"Database connection failed during {operation}"
            severity = ErrorSeverity.HIGH
        elif "constraint" in str(error).lower():
            message = f"Database constraint violation during {operation}: {str(error)}"
            severity = ErrorSeverity.MEDIUM
        elif "timeout" in str(error).lower():
            message = f"Database operation timeout during {operation}"
            severity = ErrorSeverity.MEDIUM
        else:
            message = f"Database error during {operation}: {str(error)}"
            severity = ErrorSeverity.MEDIUM
        
        db_error = DatabaseError(
            message=message,
            operation=operation,
            severity=severity,
            details={
                "original_error": str(error),
                "error_type": type(error).__name__,
                **context
            }
        )
        
        ErrorHandler.log_error(db_error, context)
        return db_error
    
    @staticmethod
    def handle_websocket_error(
        error: Exception,
        client_id: str = None,
        context: Dict[str, Any] = None
    ) -> WebSocketError:
        """Handle WebSocket connection errors"""
        context = context or {}
        
        # Determine if this is a disconnection or other error
        if "disconnect" in str(error).lower() or "connection" in str(error).lower():
            message = f"WebSocket client disconnected: {client_id or 'unknown'}"
            severity = ErrorSeverity.LOW
            recoverable = True
        else:
            message = f"WebSocket error: {str(error)}"
            severity = ErrorSeverity.MEDIUM
            recoverable = True
        
        ws_error = WebSocketError(
            message=message,
            client_id=client_id,
            severity=severity,
            recoverable=recoverable,
            details={
                "original_error": str(error),
                "error_type": type(error).__name__,
                **context
            }
        )
        
        ErrorHandler.log_error(ws_error, context)
        return ws_error
    
    @staticmethod
    def handle_configuration_error(
        config_key: str,
        error: Exception,
        context: Dict[str, Any] = None
    ) -> ConfigurationError:
        """Handle configuration validation errors"""
        context = context or {}
        
        # Create descriptive error message
        if "missing" in str(error).lower() or "required" in str(error).lower():
            message = f"Required configuration missing: {config_key}"
        elif "invalid" in str(error).lower():
            message = f"Invalid configuration value for {config_key}: {str(error)}"
        else:
            message = f"Configuration error for {config_key}: {str(error)}"
        
        config_error = ConfigurationError(
            message=message,
            config_key=config_key,
            details={
                "original_error": str(error),
                "error_type": type(error).__name__,
                **context
            }
        )
        
        ErrorHandler.log_error(config_error, context)
        return config_error


def handle_errors(
    error_category: ErrorCategory,
    reraise: bool = False,
    default_return: Any = None
):
    """Decorator for automatic error handling"""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except KodiakError:
                # Re-raise Kodiak errors as they're already handled
                raise
            except Exception as e:
                # Handle based on category
                if error_category == ErrorCategory.DATABASE:
                    handled_error = ErrorHandler.handle_database_error(
                        operation=func.__name__,
                        error=e,
                        context={"args": str(args), "kwargs": str(kwargs)}
                    )
                elif error_category == ErrorCategory.WEBSOCKET:
                    handled_error = ErrorHandler.handle_websocket_error(
                        error=e,
                        context={"function": func.__name__}
                    )
                elif error_category == ErrorCategory.CONFIGURATION:
                    handled_error = ErrorHandler.handle_configuration_error(
                        config_key=func.__name__,
                        error=e,
                        context={"args": str(args), "kwargs": str(kwargs)}
                    )
                else:
                    # Generic handling
                    handled_error = KodiakError(
                        message=f"Error in {func.__name__}: {str(e)}",
                        category=error_category,
                        details={
                            "original_error": str(e),
                            "error_type": type(e).__name__
                        }
                    )
                    ErrorHandler.log_error(handled_error)
                
                if reraise:
                    raise handled_error
                return default_return
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except KodiakError:
                # Re-raise Kodiak errors as they're already handled
                raise
            except Exception as e:
                # Handle based on category
                if error_category == ErrorCategory.DATABASE:
                    handled_error = ErrorHandler.handle_database_error(
                        operation=func.__name__,
                        error=e,
                        context={"args": str(args), "kwargs": str(kwargs)}
                    )
                elif error_category == ErrorCategory.WEBSOCKET:
                    handled_error = ErrorHandler.handle_websocket_error(
                        error=e,
                        context={"function": func.__name__}
                    )
                elif error_category == ErrorCategory.CONFIGURATION:
                    handled_error = ErrorHandler.handle_configuration_error(
                        config_key=func.__name__,
                        error=e,
                        context={"args": str(args), "kwargs": str(kwargs)}
                    )
                else:
                    # Generic handling
                    handled_error = KodiakError(
                        message=f"Error in {func.__name__}: {str(e)}",
                        category=error_category,
                        details={
                            "original_error": str(e),
                            "error_type": type(e).__name__
                        }
                    )
                    ErrorHandler.log_error(handled_error)
                
                if reraise:
                    raise handled_error
                return default_return
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def create_error_response(error: Union[Exception, KodiakError]) -> Dict[str, Any]:
    """Create a standardized error response for API endpoints"""
    if isinstance(error, KodiakError):
        return {
            "success": False,
            "error": error.to_dict()
        }
    else:
        return {
            "success": False,
            "error": {
                "message": str(error),
                "type": type(error).__name__,
                "category": "unknown",
                "severity": "medium",
                "recoverable": True
            }
        }