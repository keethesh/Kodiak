"""
Agent factory for creating KodiakAgent instances with proper dependency injection.
"""

from typing import Optional, List, Any
from kodiak.core.agent import KodiakAgent


def create_agent(
    agent_id: str,
    role: str = "generalist",
    project_id: Any = None,
    skills: Optional[List[str]] = None,
    model_name: str = None,
    session: Any = None
) -> KodiakAgent:
    """
    Create a KodiakAgent with proper dependency injection.
    
    Args:
        agent_id: Unique identifier for the agent
        role: Agent role (scout, attacker, manager, generalist)
        project_id: Project ID for the agent
        skills: List of skill names to load
        model_name: LLM model name to use
        session: Database session
    
    Returns:
        Configured KodiakAgent instance
    """
    # Get global instances
    from main import get_event_manager, get_tool_inventory
    
    event_manager = get_event_manager()
    tool_inventory = get_tool_inventory()
    
    if not event_manager:
        raise RuntimeError("EventManager not initialized. Ensure application startup completed.")
    
    if not tool_inventory:
        raise RuntimeError("ToolInventory not initialized. Ensure application startup completed.")
    
    # Create agent with dependencies
    agent = KodiakAgent(
        agent_id=agent_id,
        tool_inventory=tool_inventory,
        event_manager=event_manager,
        model_name=model_name,
        session=session,
        role=role,
        project_id=project_id,
        skills=skills
    )
    
    return agent


async def create_agent_with_hive_mind(
    agent_id: str,
    role: str = "generalist",
    project_id: Any = None,
    skills: Optional[List[str]] = None,
    model_name: str = None,
    session: Any = None
) -> KodiakAgent:
    """
    Create a KodiakAgent and register it with the Hive Mind.
    
    Args:
        agent_id: Unique identifier for the agent
        role: Agent role (scout, attacker, manager, generalist)
        project_id: Project ID for the agent
        skills: List of skill names to load
        model_name: LLM model name to use
        session: Database session
    
    Returns:
        Configured KodiakAgent instance registered with Hive Mind
    """
    agent = create_agent(
        agent_id=agent_id,
        role=role,
        project_id=project_id,
        skills=skills,
        model_name=model_name,
        session=session
    )
    
    # Register with Hive Mind for state synchronization
    await agent.register_with_hive_mind()
    
    return agent


def get_agent_dependencies():
    """
    Get the current EventManager and ToolInventory instances.
    
    Returns:
        Tuple of (event_manager, tool_inventory)
    """
    from main import get_event_manager, get_tool_inventory
    
    return get_event_manager(), get_tool_inventory()


def validate_dependencies():
    """
    Validate that all required dependencies are available.
    
    Raises:
        RuntimeError: If dependencies are not properly initialized
    """
    event_manager, tool_inventory = get_agent_dependencies()
    
    if not event_manager:
        raise RuntimeError("EventManager not initialized")
    
    if not tool_inventory:
        raise RuntimeError("ToolInventory not initialized")
    
    # Check that tools are registered
    tools = tool_inventory.list_tools()
    if not tools:
        raise RuntimeError("No tools registered in ToolInventory")
    
    return True