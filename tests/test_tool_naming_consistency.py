"""
Property-based tests for tool naming consistency.
**Feature: core-integration-fixes, Property 10: Tool naming consistency**
"""

import pytest
from kodiak.core.agent import KodiakAgent
from kodiak.core.tools.inventory import ToolInventory
from kodiak.api.events import EventManager
from kodiak.core.orchestrator import Orchestrator
from unittest.mock import Mock, AsyncMock


class TestToolNamingConsistency:
    """Test that tool names are consistent across all components"""
    
    def create_mock_event_manager(self):
        """Create a mock EventManager"""
        event_manager = Mock(spec=EventManager)
        event_manager.emit_tool_start = AsyncMock()
        event_manager.emit_tool_complete = AsyncMock()
        return event_manager
    
    def create_mock_tool_inventory(self, tools=None):
        """Create a mock ToolInventory with some tools"""
        inventory = Mock(spec=ToolInventory)
        
        # Mock some tools with realistic names
        if tools is None:
            mock_tools = {
                "nmap": "Network discovery and security auditing",
                "nuclei": "Fast vulnerability scanner",
                "subfinder": "Passive subdomain enumeration",
                "httpx": "HTTP toolkit for probing web services",
                "sqlmap": "SQL injection detection and exploitation"
            }
        else:
            mock_tools = tools
        
        inventory.list_tools.return_value = mock_tools
        
        # Mock tool instances
        mock_tool = Mock()
        mock_tool.to_openai_schema.return_value = {"type": "function", "function": {"name": "test"}}
        inventory.get.return_value = mock_tool
        
        return inventory
    
    def create_mock_orchestrator(self, available_tools=None):
        """Create a mock Orchestrator"""
        orchestrator = Mock(spec=Orchestrator)
        
        # Mock available tools in orchestrator
        if available_tools is None:
            available_tools = ["nmap", "nuclei", "subfinder", "httpx", "sqlmap"]
        
        orchestrator.get_available_tools.return_value = available_tools
        return orchestrator
    
    def test_tool_naming_consistency_across_components(self):
        """
        Property 10: Tool naming consistency
        For any tool in the system, its name should be consistent across the Tool_Inventory, Agent, and Orchestrator components.
        **Validates: Requirements 3.2**
        """
        # Define a set of test tools
        test_tools = {
            "nmap": "Network discovery and security auditing",
            "nuclei": "Fast vulnerability scanner", 
            "subfinder": "Passive subdomain enumeration",
            "httpx": "HTTP toolkit for probing web services",
            "sqlmap": "SQL injection detection and exploitation"
        }
        
        # Create mocked components
        mock_tool_inventory = self.create_mock_tool_inventory(test_tools)
        mock_event_manager = self.create_mock_event_manager()
        mock_orchestrator = self.create_mock_orchestrator(list(test_tools.keys()))
        
        # Create agent
        agent = KodiakAgent(
            agent_id="test_agent",
            tool_inventory=mock_tool_inventory,
            event_manager=mock_event_manager
        )
        
        # Get tool names from each component
        inventory_tools = set(mock_tool_inventory.list_tools().keys())
        agent_tools = set(agent.available_tools)
        orchestrator_tools = set(mock_orchestrator.get_available_tools())
        
        # Property: Tool names should be consistent across all components
        assert inventory_tools == agent_tools, (
            f"Tool names inconsistent between inventory and agent: "
            f"inventory={inventory_tools}, agent={agent_tools}"
        )
        
        assert inventory_tools == orchestrator_tools, (
            f"Tool names inconsistent between inventory and orchestrator: "
            f"inventory={inventory_tools}, orchestrator={orchestrator_tools}"
        )
        
        assert agent_tools == orchestrator_tools, (
            f"Tool names inconsistent between agent and orchestrator: "
            f"agent={agent_tools}, orchestrator={orchestrator_tools}"
        )
    
    def test_tool_name_validation_consistency(self):
        """
        Property: Tool name validation should be consistent across components
        For any tool name, all components should agree on its validity.
        **Validates: Requirements 3.2**
        """
        # Define registered tools
        registered_tools = {"nmap", "nuclei", "subfinder"}
        mock_tool_inventory = self.create_mock_tool_inventory({name: f"Description for {name}" for name in registered_tools})
        mock_event_manager = self.create_mock_event_manager()
        
        # Create agent
        agent = KodiakAgent(
            agent_id="test_agent",
            tool_inventory=mock_tool_inventory,
            event_manager=mock_event_manager
        )
        
        # Test various tool names
        test_tool_names = [
            "nmap",        # Valid tool
            "nuclei",      # Valid tool
            "subfinder",   # Valid tool
            "invalid_tool", # Invalid tool
            "unknown",     # Invalid tool
            "test123"      # Invalid tool
        ]
        
        for tool_name in test_tool_names:
            # Check consistency across components
            in_inventory = tool_name in mock_tool_inventory.list_tools()
            in_agent = tool_name in agent.available_tools
            
            # Property: All components should agree on tool validity
            assert in_inventory == in_agent, (
                f"Tool name validation inconsistency for '{tool_name}': "
                f"inventory={in_inventory}, agent={in_agent}"
            )
    
    def test_tool_name_case_sensitivity(self):
        """
        Property: Tool names should be case-sensitive and exact matches
        **Validates: Requirements 3.2**
        """
        # Define tools with specific casing
        tools = {"nmap": "Network scanner", "Nuclei": "Vuln scanner", "SubFinder": "Subdomain enum"}
        mock_tool_inventory = self.create_mock_tool_inventory(tools)
        mock_event_manager = self.create_mock_event_manager()
        
        # Create agent
        agent = KodiakAgent(
            agent_id="test_agent",
            tool_inventory=mock_tool_inventory,
            event_manager=mock_event_manager
        )
        
        # Test case variations
        case_variations = [
            ("nmap", True),      # Exact match
            ("NMAP", False),     # Wrong case
            ("Nmap", False),     # Wrong case
            ("Nuclei", True),    # Exact match
            ("nuclei", False),   # Wrong case
            ("NUCLEI", False),   # Wrong case
            ("SubFinder", True), # Exact match
            ("subfinder", False), # Wrong case
            ("SUBFINDER", False)  # Wrong case
        ]
        
        for tool_name, should_exist in case_variations:
            in_inventory = tool_name in mock_tool_inventory.list_tools()
            in_agent = tool_name in agent.available_tools
            
            # Property: Case sensitivity should be consistent
            assert in_inventory == should_exist, (
                f"Inventory case sensitivity failed for '{tool_name}': "
                f"expected {should_exist}, got {in_inventory}"
            )
            
            assert in_agent == should_exist, (
                f"Agent case sensitivity failed for '{tool_name}': "
                f"expected {should_exist}, got {in_agent}"
            )
    
    def test_tool_name_special_characters(self):
        """
        Property: Tool names with special characters should be handled consistently
        **Validates: Requirements 3.2**
        """
        # Define tools with various naming patterns
        special_tools = {
            "tool-with-dashes": "Tool with dashes",
            "tool_with_underscores": "Tool with underscores",
            "tool123": "Tool with numbers",
            "tool.with.dots": "Tool with dots"
        }
        
        mock_tool_inventory = self.create_mock_tool_inventory(special_tools)
        mock_event_manager = self.create_mock_event_manager()
        
        # Create agent
        agent = KodiakAgent(
            agent_id="test_agent",
            tool_inventory=mock_tool_inventory,
            event_manager=mock_event_manager
        )
        
        # Property: All special character tool names should be handled consistently
        inventory_tools = set(mock_tool_inventory.list_tools().keys())
        agent_tools = set(agent.available_tools)
        
        assert inventory_tools == agent_tools, (
            f"Special character tool names not handled consistently: "
            f"inventory={inventory_tools}, agent={agent_tools}"
        )
        
        # Verify each special tool name individually
        for tool_name in special_tools.keys():
            assert tool_name in agent.available_tools, (
                f"Special character tool '{tool_name}' not available in agent"
            )
    
    def test_empty_tool_name_handling(self):
        """
        Property: Empty or None tool names should be handled gracefully
        **Validates: Requirements 3.2**
        """
        # Test with tools that might have problematic names
        problematic_tools = {
            "valid_tool": "Valid tool description"
            # Note: We can't actually test empty string keys in dict, 
            # but we can test the agent's handling of such cases
        }
        
        mock_tool_inventory = self.create_mock_tool_inventory(problematic_tools)
        mock_event_manager = self.create_mock_event_manager()
        
        # Create agent
        agent = KodiakAgent(
            agent_id="test_agent",
            tool_inventory=mock_tool_inventory,
            event_manager=mock_event_manager
        )
        
        # Test edge cases
        edge_cases = ["", None, " ", "\t", "\n"]
        
        for edge_case in edge_cases:
            # Property: Edge cases should not be in available tools
            if edge_case is not None:
                assert edge_case not in agent.available_tools, (
                    f"Edge case '{repr(edge_case)}' should not be in available tools"
                )
    
    def test_tool_name_uniqueness_property(self):
        """
        Property: Tool names should be unique within each component
        **Validates: Requirements 3.2**
        """
        # Define tools (ensuring uniqueness)
        tools = {
            "nmap": "Network scanner",
            "nuclei": "Vulnerability scanner", 
            "subfinder": "Subdomain enumeration",
            "httpx": "HTTP prober",
            "sqlmap": "SQL injection tool"
        }
        
        mock_tool_inventory = self.create_mock_tool_inventory(tools)
        mock_event_manager = self.create_mock_event_manager()
        
        # Create agent
        agent = KodiakAgent(
            agent_id="test_agent",
            tool_inventory=mock_tool_inventory,
            event_manager=mock_event_manager
        )
        
        # Property: Tool names should be unique (no duplicates)
        inventory_tools = list(mock_tool_inventory.list_tools().keys())
        agent_tools = list(agent.available_tools)
        
        # Check for uniqueness
        assert len(inventory_tools) == len(set(inventory_tools)), (
            f"Duplicate tool names in inventory: {inventory_tools}"
        )
        
        assert len(agent_tools) == len(set(agent_tools)), (
            f"Duplicate tool names in agent: {agent_tools}"
        )
        
        # Property: Same tools should appear in both
        assert set(inventory_tools) == set(agent_tools), (
            f"Tool name sets don't match: inventory={set(inventory_tools)}, agent={set(agent_tools)}"
        )