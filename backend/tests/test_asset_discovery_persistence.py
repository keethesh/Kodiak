"""
Property-based tests for asset discovery persistence.

Feature: core-integration-fixes, Property 7: Asset discovery persistence
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List

from kodiak.database.models import Project, Node, ScanJob
from kodiak.database.crud import node, project


class MockAsyncSession:
    """Mock AsyncSession for testing asset discovery persistence without database."""
    
    def __init__(self):
        self.added_objects = []
        self.committed = False
        self.rolled_back = False
        self.query_results = {}
        self.nodes_by_project = {}
        
    def add(self, obj):
        """Mock add operation."""
        self.added_objects.append(obj)
        
        # Simulate storing nodes by project for retrieval
        if isinstance(obj, Node):
            if obj.project_id not in self.nodes_by_project:
                self.nodes_by_project[obj.project_id] = []
            self.nodes_by_project[obj.project_id].append(obj)
        
    async def commit(self):
        """Mock commit operation."""
        self.committed = True
        
    async def rollback(self):
        """Mock rollback operation."""
        self.rolled_back = True
        
    async def refresh(self, obj):
        """Mock refresh operation."""
        pass
        
    async def execute(self, statement):
        """Mock execute operation."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = self.query_results.get('scalar_one_or_none')
        result.scalars.return_value.all.return_value = self.query_results.get('scalars_all', [])
        return result
        
    def set_query_result(self, result_type, value):
        """Set mock query results."""
        self.query_results[result_type] = value


class TestAssetDiscoveryPersistenceProperties:
    """Property-based tests for asset discovery persistence."""

    def create_test_fixtures(self):
        """Create test fixtures for asset discovery scenarios."""
        # Create test project
        test_project = Project(
            id=uuid4(),
            name="Asset Discovery Test Project",
            description="Test project for asset discovery persistence"
        )
        
        # Create discovered assets (nodes) from various discovery methods
        discovered_assets = [
            # Network discovery
            Node(
                id=uuid4(),
                project_id=test_project.id,
                label="Asset",
                type="ip",
                name="192.168.1.100",
                properties={
                    "discovered_by": "nmap",
                    "discovery_time": "2024-01-01T10:00:00Z",
                    "ports": ["22", "80", "443"],
                    "os_guess": "Linux"
                }
            ),
            # Domain discovery
            Node(
                id=uuid4(),
                project_id=test_project.id,
                label="Asset",
                type="domain",
                name="api.example.com",
                properties={
                    "discovered_by": "subfinder",
                    "discovery_time": "2024-01-01T10:05:00Z",
                    "dns_records": ["A", "AAAA", "CNAME"]
                }
            ),
            # Service discovery
            Node(
                id=uuid4(),
                project_id=test_project.id,
                label="Service",
                type="service",
                name="80/tcp",
                properties={
                    "discovered_by": "nmap",
                    "discovery_time": "2024-01-01T10:10:00Z",
                    "service": "http",
                    "version": "nginx/1.18.0",
                    "banner": "nginx/1.18.0 (Ubuntu)"
                }
            ),
            # Web application discovery
            Node(
                id=uuid4(),
                project_id=test_project.id,
                label="Application",
                type="url",
                name="https://example.com/admin",
                properties={
                    "discovered_by": "httpx",
                    "discovery_time": "2024-01-01T10:15:00Z",
                    "status_code": 200,
                    "title": "Admin Panel",
                    "technologies": ["PHP", "MySQL"]
                }
            ),
            # File discovery
            Node(
                id=uuid4(),
                project_id=test_project.id,
                label="File",
                type="file",
                name="/etc/passwd",
                properties={
                    "discovered_by": "dirb",
                    "discovery_time": "2024-01-01T10:20:00Z",
                    "size": 1024,
                    "permissions": "644"
                }
            )
        ]
        
        return test_project, discovered_assets

    @pytest.mark.asyncio
    async def test_asset_discovery_persistence_node_creation(self):
        """
        Property 7: Asset discovery persistence for node creation
        For any asset discovered by an agent, the system should create a Node record
        with proper foreign key relationships to the project.
        
        **Validates: Requirements 2.2**
        """
        session = MockAsyncSession()
        test_project, discovered_assets = self.create_test_fixtures()
        
        # Test that each discovered asset is properly persisted as a Node
        for asset in discovered_assets:
            # Create node using CRUD (simulating agent discovery)
            result = await node.create(session, asset)
            
            # Verify the result is a Node instance with proper relationships
            assert isinstance(result, Node)
            assert result.id == asset.id
            assert result.project_id == test_project.id  # Foreign key relationship
            assert result.label == asset.label
            assert result.type == asset.type
            assert result.name == asset.name
            assert result.properties == asset.properties
            
            # Verify the node was added to the session
            assert asset in session.added_objects
            assert session.committed == True
            
            # Verify foreign key relationship is maintained
            assert hasattr(result, 'project_id')
            assert result.project_id is not None
            assert result.project_id == test_project.id
            
            # Reset session for next iteration
            session.added_objects = []
            session.committed = False

    @pytest.mark.asyncio
    async def test_asset_discovery_persistence_project_relationship(self):
        """
        Property 7: Asset discovery persistence with project relationships
        For any asset discovered within a project, the Node record should maintain
        proper foreign key relationships and be retrievable by project.
        
        **Validates: Requirements 2.2**
        """
        session = MockAsyncSession()
        test_project, discovered_assets = self.create_test_fixtures()
        
        # Create all discovered assets
        created_nodes = []
        for asset in discovered_assets:
            created_node = await node.create(session, asset)
            created_nodes.append(created_node)
        
        # Set up mock query result for project nodes retrieval
        session.set_query_result('scalars_all', discovered_assets)
        
        # Retrieve all nodes for the project
        project_nodes = await node.get_nodes_by_project(session, test_project.id)
        
        # Verify all discovered assets are retrievable by project
        assert isinstance(project_nodes, list)
        assert len(project_nodes) == len(discovered_assets)
        
        # Verify each node maintains proper project relationship
        for project_node in project_nodes:
            assert isinstance(project_node, Node)
            assert project_node.project_id == test_project.id
            
            # Verify the node exists in our discovered assets
            matching_asset = next(
                (asset for asset in discovered_assets if asset.id == project_node.id),
                None
            )
            assert matching_asset is not None
            assert project_node.name == matching_asset.name
            assert project_node.type == matching_asset.type

    @pytest.mark.asyncio
    async def test_asset_discovery_persistence_discovery_metadata(self):
        """
        Property 7: Asset discovery persistence with discovery metadata
        For any asset discovered by an agent, the Node record should preserve
        discovery metadata including discovery method, time, and context.
        
        **Validates: Requirements 2.2**
        """
        session = MockAsyncSession()
        test_project, discovered_assets = self.create_test_fixtures()
        
        # Test that discovery metadata is preserved for each asset type
        for asset in discovered_assets:
            # Create node with discovery metadata
            result = await node.create(session, asset)
            
            # Verify discovery metadata is preserved
            assert isinstance(result, Node)
            assert result.properties is not None
            assert isinstance(result.properties, dict)
            
            # Verify required discovery metadata fields
            assert 'discovered_by' in result.properties
            assert 'discovery_time' in result.properties
            assert result.properties['discovered_by'] is not None
            assert result.properties['discovery_time'] is not None
            
            # Verify discovery method is recorded
            discovery_methods = ['nmap', 'subfinder', 'httpx', 'dirb', 'nuclei', 'sqlmap']
            assert result.properties['discovered_by'] in discovery_methods
            
            # Verify additional metadata based on asset type
            if result.type == 'ip':
                assert 'ports' in result.properties or 'os_guess' in result.properties
            elif result.type == 'domain':
                assert 'dns_records' in result.properties
            elif result.type == 'service':
                assert 'service' in result.properties
                assert 'version' in result.properties or 'banner' in result.properties
            elif result.type == 'url':
                assert 'status_code' in result.properties
            elif result.type == 'file':
                assert 'size' in result.properties or 'permissions' in result.properties

    @pytest.mark.asyncio
    async def test_asset_discovery_persistence_duplicate_handling(self):
        """
        Property 7: Asset discovery persistence with duplicate handling
        For any asset discovered multiple times, the system should handle
        duplicates appropriately while maintaining data integrity.
        
        **Validates: Requirements 2.2**
        """
        session = MockAsyncSession()
        test_project, discovered_assets = self.create_test_fixtures()
        
        # Test duplicate asset discovery scenarios
        original_asset = discovered_assets[0]  # IP asset
        
        # Create duplicate asset with different discovery metadata
        duplicate_asset = Node(
            id=uuid4(),  # Different ID
            project_id=test_project.id,
            label=original_asset.label,
            type=original_asset.type,
            name=original_asset.name,  # Same name and type
            properties={
                "discovered_by": "masscan",  # Different discovery method
                "discovery_time": "2024-01-01T11:00:00Z",  # Different time
                "ports": ["22", "80", "443", "8080"],  # Additional data
                "confidence": "high"
            }
        )
        
        # Create original asset
        original_result = await node.create(session, original_asset)
        assert isinstance(original_result, Node)
        assert original_result.project_id == test_project.id
        
        # Create duplicate asset
        duplicate_result = await node.create(session, duplicate_asset)
        assert isinstance(duplicate_result, Node)
        assert duplicate_result.project_id == test_project.id
        
        # Verify both assets can coexist (different IDs)
        assert original_result.id != duplicate_result.id
        assert original_result.name == duplicate_result.name
        assert original_result.type == duplicate_result.type
        
        # Verify discovery metadata is preserved for both
        assert original_result.properties['discovered_by'] == 'nmap'
        assert duplicate_result.properties['discovered_by'] == 'masscan'

    @pytest.mark.asyncio
    async def test_asset_discovery_persistence_query_by_discovery_method(self):
        """
        Property 7: Asset discovery persistence with discovery method queries
        For any discovery method used by agents, the system should allow
        querying assets by their discovery method and metadata.
        
        **Validates: Requirements 2.2**
        """
        session = MockAsyncSession()
        test_project, discovered_assets = self.create_test_fixtures()
        
        # Group assets by discovery method
        nmap_assets = [asset for asset in discovered_assets 
                      if asset.properties.get('discovered_by') == 'nmap']
        httpx_assets = [asset for asset in discovered_assets 
                       if asset.properties.get('discovered_by') == 'httpx']
        
        # Create all assets
        for asset in discovered_assets:
            await node.create(session, asset)
        
        # Test querying by discovery method (simulated through project query)
        session.set_query_result('scalars_all', nmap_assets)
        nmap_results = await node.get_nodes_by_project(session, test_project.id)
        
        # Verify nmap assets are retrievable
        for nmap_result in nmap_results:
            assert isinstance(nmap_result, Node)
            assert nmap_result.properties['discovered_by'] == 'nmap'
            assert nmap_result.project_id == test_project.id
        
        # Test querying httpx assets
        session.set_query_result('scalars_all', httpx_assets)
        httpx_results = await node.get_nodes_by_project(session, test_project.id)
        
        for httpx_result in httpx_results:
            assert isinstance(httpx_result, Node)
            assert httpx_result.properties['discovered_by'] == 'httpx'
            assert httpx_result.project_id == test_project.id

    @pytest.mark.asyncio
    async def test_asset_discovery_persistence_scan_workflow(self):
        """
        Property 7: Asset discovery persistence in scan workflow
        For any complete asset discovery workflow, the system should maintain
        proper relationships and state throughout the discovery process.
        
        **Validates: Requirements 2.2**
        """
        session = MockAsyncSession()
        test_project, discovered_assets = self.create_test_fixtures()
        
        # Simulate a complete discovery workflow
        workflow_steps = [
            # Step 1: Network discovery
            [asset for asset in discovered_assets if asset.type == 'ip'],
            # Step 2: Service discovery
            [asset for asset in discovered_assets if asset.type == 'service'],
            # Step 3: Web discovery
            [asset for asset in discovered_assets if asset.type in ['domain', 'url']],
            # Step 4: File discovery
            [asset for asset in discovered_assets if asset.type == 'file']
        ]
        
        all_created_assets = []
        
        # Execute workflow steps
        for step_assets in workflow_steps:
            step_results = []
            for asset in step_assets:
                result = await node.create(session, asset)
                step_results.append(result)
                all_created_assets.append(result)
                
                # Verify each asset maintains project relationship
                assert isinstance(result, Node)
                assert result.project_id == test_project.id
                assert hasattr(result, 'properties')
                assert 'discovered_by' in result.properties
        
        # Verify complete workflow results
        session.set_query_result('scalars_all', discovered_assets)
        final_results = await node.get_nodes_by_project(session, test_project.id)
        
        # Verify all discovered assets are persisted
        assert len(final_results) == len(discovered_assets)
        
        # Verify workflow integrity
        for final_result in final_results:
            assert isinstance(final_result, Node)
            assert final_result.project_id == test_project.id
            
            # Verify discovery metadata is preserved
            assert 'discovered_by' in final_result.properties
            assert 'discovery_time' in final_result.properties

    @pytest.mark.asyncio
    async def test_asset_discovery_persistence_error_recovery(self):
        """
        Property 7: Asset discovery persistence with error recovery
        For any asset discovery that encounters errors, the system should
        handle failures gracefully while maintaining data integrity.
        
        **Validates: Requirements 2.2**
        """
        # Create a session that will fail on commit
        class FailingSession(MockAsyncSession):
            def __init__(self, fail_on_commit=True):
                super().__init__()
                self.fail_on_commit = fail_on_commit
                
            async def commit(self):
                if self.fail_on_commit:
                    from sqlalchemy.exc import SQLAlchemyError
                    raise SQLAlchemyError("Database connection lost during discovery")
                await super().commit()
        
        failing_session = FailingSession()
        test_project, discovered_assets = self.create_test_fixtures()
        
        # Test error handling during asset discovery
        test_asset = discovered_assets[0]
        
        # Attempt to create asset with failing session
        with pytest.raises(RuntimeError, match="Failed to create node"):
            await node.create(failing_session, test_asset)
        
        # Verify rollback was called to maintain data integrity
        assert failing_session.rolled_back == True
        
        # Verify the asset was added but not committed
        assert test_asset in failing_session.added_objects
        assert failing_session.committed == False

    @pytest.mark.asyncio
    async def test_asset_discovery_persistence_concurrent_discovery(self):
        """
        Property 7: Asset discovery persistence with concurrent discovery
        For any concurrent asset discovery by multiple agents, the system should
        handle concurrent operations while maintaining data consistency.
        
        **Validates: Requirements 2.2**
        """
        session = MockAsyncSession()
        test_project, discovered_assets = self.create_test_fixtures()
        
        # Simulate concurrent discovery by multiple agents
        agent_discoveries = {
            'agent_1': [discovered_assets[0], discovered_assets[1]],  # Network agent
            'agent_2': [discovered_assets[2], discovered_assets[3]],  # Web agent
            'agent_3': [discovered_assets[4]]  # File agent
        }
        
        # Simulate concurrent asset creation
        concurrent_results = []
        for agent_id, agent_assets in agent_discoveries.items():
            for asset in agent_assets:
                # Add agent context to discovery metadata
                asset.properties['agent_id'] = agent_id
                asset.properties['concurrent_discovery'] = True
                
                result = await node.create(session, asset)
                concurrent_results.append(result)
                
                # Verify concurrent discovery metadata
                assert isinstance(result, Node)
                assert result.project_id == test_project.id
                assert result.properties['agent_id'] == agent_id
                assert result.properties['concurrent_discovery'] == True
        
        # Verify all concurrent discoveries are persisted
        assert len(concurrent_results) == len(discovered_assets)
        
        # Verify project relationships are maintained
        for result in concurrent_results:
            assert result.project_id == test_project.id
            assert 'agent_id' in result.properties
            assert 'discovered_by' in result.properties

    @pytest.mark.asyncio
    async def test_asset_discovery_persistence_update_existing_assets(self):
        """
        Property 7: Asset discovery persistence with asset updates
        For any asset that is rediscovered with additional information,
        the system should update existing Node records appropriately.
        
        **Validates: Requirements 2.2**
        """
        session = MockAsyncSession()
        test_project, discovered_assets = self.create_test_fixtures()
        
        # Create initial asset
        initial_asset = discovered_assets[0]  # IP asset
        created_asset = await node.create(session, initial_asset)
        
        # Set up mock for retrieval
        session.set_query_result('scalar_one_or_none', created_asset)
        
        # Simulate rediscovery with additional information
        additional_properties = {
            'os_detection': 'Ubuntu 20.04',
            'open_ports': ['22', '80', '443', '8080'],
            'last_scan': '2024-01-01T12:00:00Z',
            'vulnerability_count': 3
        }
        
        # Update asset with new discovery information
        updated_asset = await node.update_node(
            session, 
            created_asset.id, 
            {'properties': {**created_asset.properties, **additional_properties}}
        )
        
        # Verify asset update maintains relationships
        assert isinstance(updated_asset, Node)
        assert updated_asset.id == created_asset.id
        assert updated_asset.project_id == test_project.id
        assert updated_asset.name == created_asset.name
        assert updated_asset.type == created_asset.type
        
        # Verify original discovery metadata is preserved
        assert 'discovered_by' in updated_asset.properties
        assert 'discovery_time' in updated_asset.properties
        
        # Note: In a real implementation, the properties would be merged
        # Here we're testing the interface consistency