"""
Property-based tests for tool availability consistency.
**Feature: core-integration-fixes, Property 9: Tool availability consistency**
"""

import pytest
from kodiak.core.agent import KodiakAgent
from kodiak.core.tools.inventory import ToolInventory
from kodiak.api.events import EventManager
from unittest.mock import Mock, AsyncMock


class TestToolAvailabilityConsistency:
    """Test that agents have access to all registered tools"""
    
    def create_mock_event_manager(self):
        """Create a mock EventManager"""
        event_manager = Mock(spec=EventManager)
        event_manager.emit_tool_start = AsyncMock()
        event_manager.emit_tool_complete = AsyncMock()
        return event_manager
    
    def create_mock_tool_inventory(self, tools=None):
        """Create a mock ToolInventory with some tools"""
        inventory = Mock(spec=ToolInventory)
        
        # Mock some tools
        if tools is None:
            mock_tools = {
                "nmap": "Network discovery and security auditing",
                "nuclei": "Fast vulnerability scanner",
                "subfinder": "Passive subdomain enumeration"
            }
        else:
            mock_tools = tools
        
        inventory.list_tools.return_value = mock_tools
        
        # Mock tool instances
        mock_tool = Mock()
        mock_tool.to_openai_schema.return_value = {"type": "function", "function": {"name": "test"}}
        inventory.get.return_value = mock_tool
        
        return inventory
    
    def test_agent_has_access_to_all_registered_tools_property(self):
        """
        Property 9: Tool availability consistency
        For any agent in the system, it should have access to all tools registered in the Tool_Inventory.
        **Validates: Requirements 3.1**
        """
        # Test with multiple agent configurations
        test_cases = [
            ("agent1", "scout"),
            ("agent2", "attacker"), 
            ("agent3", "manager"),
            ("agent4", "generalist"),
            ("test_agent_123", "scout")
        ]
        
        for agent_id, role in test_cases:
            # Create mocks for each test case
            mock_tool_inventory = self.create_mock_tool_inventory()
            mock_event_manager = self.create_mock_event_manager()
            
            # Create agent with mocked dependencies
            agent = KodiakAgent(
                agent_id=agent_id,
                tool_inventory=mock_tool_inventory,
                event_manager=mock_event_manager,
                role=role
            )
            
            # Get registered tools from inventory
            registered_tools = set(mock_tool_inventory.list_tools().keys())
            
            # Get available tools from agent
            available_tools = set(agent.available_tools)
            
            # Property: Agent should have access to all registered tools
            assert available_tools == registered_tools, (
                f"Agent {agent_id} does not have access to all registered tools. "
                f"Missing: {registered_tools - available_tools}, "
                f"Extra: {available_tools - registered_tools}"
            )
    
    def test_agent_tool_validation_consistency_property(self):
        """
        Property: Tool validation should be consistent with inventory
        For any tool name, agent validation should match inventory availability.
        **Validates: Requirements 3.1**
        """
        # Setup mock inventory
        registered_tools = {"nmap", "nuclei", "subfinder"}
        mock_tool_inventory = self.create_mock_tool_inventory({name: f"Description for {name}" for name in registered_tools})
        mock_event_manager = self.create_mock_event_manager()
        
        # Test with multiple tool names
        test_tool_names = ["nmap", "nuclei", "subfinder", "unknown_tool", "invalid", "test123"]
        
        for tool_name in test_tool_names:
            # Create agent
            agent = KodiakAgent(
                agent_id=f"agent_for_{tool_name}",
                tool_inventory=mock_tool_inventory,
                event_manager=mock_event_manager
            )
            
            # Check consistency
            tool_in_inventory = tool_name in registered_tools
            tool_in_agent = tool_name in agent.available_tools
            
            # Property: Agent tool availability should match inventory
            assert tool_in_inventory == tool_in_agent, (
                f"Tool availability inconsistency for '{tool_name}': "
                f"in_inventory={tool_in_inventory}, in_agent={tool_in_agent}"
            )

    def test_empty_inventory_handling(self):
        """Test agent behavior with empty tool inventory"""
        # Create empty inventory
        empty_inventory = self.create_mock_tool_inventory({})
        mock_event_manager = self.create_mock_event_manager()
        
        # Create agent
        agent = KodiakAgent(
            agent_id="test_agent",
            tool_inventory=empty_inventory,
            event_manager=mock_event_manager
        )
        
        # Property: Agent should handle empty inventory gracefully
        assert agent.available_tools == []
        assert len(agent.available_tools) == 0

    def test_agent_tool_access_after_inventory_update(self):
        """Test that agent tool access reflects inventory state"""
        # Create inventory with initial tools
        initial_tools = {"nmap": "Network scanner"}
        inventory = self.create_mock_tool_inventory(initial_tools)
        mock_event_manager = self.create_mock_event_manager()
        
        # Create agent
        agent = KodiakAgent(
            agent_id="test_agent",
            tool_inventory=inventory,
            event_manager=mock_event_manager
        )
        
        # Verify initial state
        assert set(agent.available_tools) == set(initial_tools.keys())
        
        # Update inventory (simulate tool registration)
        updated_tools = {"nmap": "Network scanner", "nuclei": "Vulnerability scanner"}
        updated_inventory = self.create_mock_tool_inventory(updated_tools)
        
        # Create new agent (simulating agent creation after inventory update)
        new_agent = KodiakAgent(
            agent_id="test_agent_2",
            tool_inventory=updated_inventory,
            event_manager=mock_event_manager
        )
        
        # Property: New agent should have access to updated tool set
        assert set(new_agent.available_tools) == set(updated_tools.keys())

    def test_multiple_agents_same_inventory_consistency(self):
        """
        Property: Multiple agents using the same inventory should have identical tool access
        **Validates: Requirements 3.1**
        """
        # Create shared inventory
        shared_tools = {"nmap": "Network scanner", "nuclei": "Vuln scanner", "httpx": "HTTP prober"}
        shared_inventory = self.create_mock_tool_inventory(shared_tools)
        mock_event_manager = self.create_mock_event_manager()
        
        # Create multiple agents
        agents = []
        for i in range(5):
            agent = KodiakAgent(
                agent_id=f"agent_{i}",
                tool_inventory=shared_inventory,
                event_manager=mock_event_manager,
                role=["scout", "attacker", "manager", "generalist"][i % 4]
            )
            agents.append(agent)
        
        # Property: All agents should have identical tool access
        expected_tools = set(shared_tools.keys())
        for agent in agents:
            assert set(agent.available_tools) == expected_tools, (
                f"Agent {agent.agent_id} has inconsistent tool access: "
                f"expected {expected_tools}, got {set(agent.available_tools)}"
            )