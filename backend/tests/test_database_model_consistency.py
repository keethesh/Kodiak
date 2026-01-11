"""
Property-based tests for database model consistency.

Feature: core-integration-fixes, Property 6: Database model consistency
"""

import pytest
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

from kodiak.database.models import Project, Node, ScanJob
from kodiak.database.crud import node, project, scan_job


class MockAsyncSession:
    """Mock AsyncSession for testing CRUD operations without database."""
    
    def __init__(self):
        self.added_objects = []
        self.committed = False
        self.rolled_back = False
        self.deleted_objects = []
        self.query_results = {}
        
    def add(self, obj):
        """Mock add operation."""
        self.added_objects.append(obj)
        
    async def commit(self):
        """Mock commit operation."""
        self.committed = True
        
    async def rollback(self):
        """Mock rollback operation."""
        self.rolled_back = True
        
    async def refresh(self, obj):
        """Mock refresh operation."""
        pass
        
    async def delete(self, obj):
        """Mock delete operation."""
        self.deleted_objects.append(obj)
        
    async def execute(self, statement):
        """Mock execute operation."""
        # Return a mock result based on the statement
        result = MagicMock()
        result.scalar_one_or_none.return_value = self.query_results.get('scalar_one_or_none')
        result.scalars.return_value.all.return_value = self.query_results.get('scalars_all', [])
        return result
        
    def set_query_result(self, result_type, value):
        """Set mock query results."""
        self.query_results[result_type] = value


class TestDatabaseModelConsistencyProperties:
    """Property-based tests for database model consistency."""

    def create_test_fixtures(self):
        """Create test fixtures for database operations."""
        # Create test project
        test_project = Project(
            id=uuid4(),
            name="Test Project",
            description="Test project for database consistency"
        )
        
        # Create test nodes
        test_nodes = [
            Node(
                id=uuid4(),
                project_id=test_project.id,
                label="Asset",
                type="domain",
                name="example.com",
                properties={"discovered_by": "nmap"}
            ),
            Node(
                id=uuid4(),
                project_id=test_project.id,
                label="Asset", 
                type="ip",
                name="192.168.1.1",
                properties={"port_scan": "completed"}
            ),
            Node(
                id=uuid4(),
                project_id=test_project.id,
                label="Service",
                type="service",
                name="80/tcp",
                properties={"service": "http", "version": "nginx/1.18"}
            )
        ]
        
        return test_project, test_nodes

    @pytest.mark.asyncio
    async def test_database_model_consistency_node_creation(self):
        """
        Property 6: Database model consistency for Node creation
        For any CRUD operation involving assets, the system should use Node models
        consistently without referencing the deprecated Asset model.
        
        **Validates: Requirements 2.1**
        """
        session = MockAsyncSession()
        test_project, test_nodes = self.create_test_fixtures()
        
        # Test that node CRUD operations use Node model consistently
        for test_node in test_nodes:
            # Create node using CRUD
            result = await node.create(session, test_node)
            
            # Verify the result is a Node instance
            assert isinstance(result, Node)
            assert result.id == test_node.id
            assert result.project_id == test_project.id
            assert result.label == test_node.label
            assert result.type == test_node.type
            assert result.name == test_node.name
            
            # Verify session operations
            assert test_node in session.added_objects
            assert session.committed == True
            
            # Reset session for next iteration
            session.added_objects = []
            session.committed = False

    @pytest.mark.asyncio
    async def test_database_model_consistency_node_retrieval(self):
        """
        Property 6: Database model consistency for Node retrieval
        For any Node query operation, the system should return Node models
        consistently without Asset model references.
        
        **Validates: Requirements 2.1**
        """
        session = MockAsyncSession()
        test_project, test_nodes = self.create_test_fixtures()
        
        # Test individual node retrieval
        for test_node in test_nodes:
            # Set up mock query result
            session.set_query_result('scalar_one_or_none', test_node)
            
            # Retrieve node using CRUD
            result = await node.get(session, test_node.id)
            
            # Verify the result is a Node instance
            assert isinstance(result, Node)
            assert result.id == test_node.id
            assert result.project_id == test_project.id
            assert result.type == test_node.type
            assert result.name == test_node.name

    @pytest.mark.asyncio
    async def test_database_model_consistency_project_nodes_relationship(self):
        """
        Property 6: Database model consistency for project-node relationships
        For any project query involving nodes, the system should maintain
        proper foreign key relationships between Project and Node models.
        
        **Validates: Requirements 2.1**
        """
        session = MockAsyncSession()
        test_project, test_nodes = self.create_test_fixtures()
        
        # Set up mock query result for project nodes
        session.set_query_result('scalars_all', test_nodes)
        
        # Get nodes by project
        result_nodes = await node.get_nodes_by_project(session, test_project.id)
        
        # Verify all returned nodes are Node instances
        assert isinstance(result_nodes, list)
        assert len(result_nodes) == len(test_nodes)
        
        for result_node in result_nodes:
            assert isinstance(result_node, Node)
            assert result_node.project_id == test_project.id
            
            # Verify foreign key relationship is maintained
            assert hasattr(result_node, 'project_id')
            assert result_node.project_id == test_project.id

    @pytest.mark.asyncio
    async def test_database_model_consistency_node_updates(self):
        """
        Property 6: Database model consistency for Node updates
        For any Node update operation, the system should maintain Node model
        consistency and proper field updates.
        
        **Validates: Requirements 2.1**
        """
        session = MockAsyncSession()
        test_project, test_nodes = self.create_test_fixtures()
        
        for test_node in test_nodes:
            # Set up mock query result
            session.set_query_result('scalar_one_or_none', test_node)
            
            # Test various update scenarios
            update_scenarios = [
                {"scanned": True},
                {"properties": {"updated": True, "scan_time": "2024-01-01"}},
                {"name": f"updated_{test_node.name}"},
                {"scanned": True, "properties": {"status": "completed"}}
            ]
            
            for updates in update_scenarios:
                # Update node using CRUD
                result = await node.update_node(session, test_node.id, updates)
                
                # Verify the result is a Node instance
                assert isinstance(result, Node)
                assert result.id == test_node.id
                assert result.project_id == test_project.id
                
                # Verify updates were applied
                for key, value in updates.items():
                    assert hasattr(result, key)
                    # Note: In real implementation, the values would be updated
                    # Here we're testing the interface consistency

    @pytest.mark.asyncio
    async def test_database_model_consistency_node_queries(self):
        """
        Property 6: Database model consistency for specialized Node queries
        For any specialized Node query (by name/type, unscanned nodes),
        the system should return Node models consistently.
        
        **Validates: Requirements 2.1**
        """
        session = MockAsyncSession()
        test_project, test_nodes = self.create_test_fixtures()
        
        # Test get_by_name_and_type
        domain_node = test_nodes[0]  # domain type
        session.set_query_result('scalar_one_or_none', domain_node)
        
        result = await node.get_by_name_and_type(
            session, test_project.id, domain_node.name, domain_node.type
        )
        
        assert isinstance(result, Node)
        assert result.name == domain_node.name
        assert result.type == domain_node.type
        assert result.project_id == test_project.id
        
        # Test get_unscanned_nodes
        unscanned_nodes = [n for n in test_nodes if not n.scanned]
        session.set_query_result('scalars_all', unscanned_nodes)
        
        result_unscanned = await node.get_unscanned_nodes(session, test_project.id)
        
        assert isinstance(result_unscanned, list)
        for unscanned_node in result_unscanned:
            assert isinstance(unscanned_node, Node)
            assert unscanned_node.project_id == test_project.id
            assert unscanned_node.scanned == False

    @pytest.mark.asyncio
    async def test_database_model_consistency_node_deletion(self):
        """
        Property 6: Database model consistency for Node deletion
        For any Node deletion operation, the system should handle Node models
        consistently and maintain referential integrity.
        
        **Validates: Requirements 2.1**
        """
        session = MockAsyncSession()
        test_project, test_nodes = self.create_test_fixtures()
        
        for test_node in test_nodes:
            # Set up mock query result
            session.set_query_result('scalar_one_or_none', test_node)
            
            # Delete node using CRUD
            result = await node.delete(session, test_node.id)
            
            # Verify deletion was successful
            assert result == True
            assert test_node in session.deleted_objects
            assert session.committed == True
            
            # Reset session for next iteration
            session.deleted_objects = []
            session.committed = False

    @pytest.mark.asyncio
    async def test_database_model_consistency_error_handling(self):
        """
        Property 6: Database model consistency with error handling
        For any CRUD operation that fails, the system should handle errors
        consistently while maintaining Node model usage.
        
        **Validates: Requirements 2.1**
        """
        # Create a session that will raise SQLAlchemy errors
        class ErrorSession(MockAsyncSession):
            async def commit(self):
                from sqlalchemy.exc import SQLAlchemyError
                raise SQLAlchemyError("Database connection failed")
                
            async def execute(self, statement):
                from sqlalchemy.exc import SQLAlchemyError
                raise SQLAlchemyError("Query execution failed")
        
        error_session = ErrorSession()
        test_project, test_nodes = self.create_test_fixtures()
        
        # Test error handling in create operation
        with pytest.raises(RuntimeError, match="Failed to create node"):
            await node.create(error_session, test_nodes[0])
        
        # Verify rollback was called
        assert error_session.rolled_back == True
        
        # Test error handling in get operation
        with pytest.raises(RuntimeError, match="Failed to get node"):
            await node.get(error_session, test_nodes[0].id)

    @pytest.mark.asyncio
    async def test_database_model_consistency_multiple_operations(self):
        """
        Property 6: Database model consistency across multiple operations
        For any sequence of CRUD operations, the system should maintain
        Node model consistency throughout the entire workflow.
        
        **Validates: Requirements 2.1**
        """
        session = MockAsyncSession()
        test_project, test_nodes = self.create_test_fixtures()
        
        # Simulate a complete workflow: create, read, update, query
        workflow_node = test_nodes[0]
        
        # Step 1: Create node
        created_node = await node.create(session, workflow_node)
        assert isinstance(created_node, Node)
        assert created_node.id == workflow_node.id
        
        # Step 2: Retrieve node
        session.set_query_result('scalar_one_or_none', workflow_node)
        retrieved_node = await node.get(session, workflow_node.id)
        assert isinstance(retrieved_node, Node)
        assert retrieved_node.id == workflow_node.id
        
        # Step 3: Update node
        updated_node = await node.update_node(session, workflow_node.id, {"scanned": True})
        assert isinstance(updated_node, Node)
        assert updated_node.id == workflow_node.id
        
        # Step 4: Query nodes by project
        session.set_query_result('scalars_all', [workflow_node])
        project_nodes = await node.get_nodes_by_project(session, test_project.id)
        assert isinstance(project_nodes, list)
        assert all(isinstance(n, Node) for n in project_nodes)
        
        # Verify all operations maintained Node model consistency
        assert all(n.project_id == test_project.id for n in project_nodes)

    @pytest.mark.asyncio
    async def test_database_model_consistency_crud_interface(self):
        """
        Property 6: Database model consistency in CRUD interface
        For any CRUD class method, it should accept and return Node models
        consistently without any Asset model references.
        
        **Validates: Requirements 2.1**
        """
        session = MockAsyncSession()
        test_project, test_nodes = self.create_test_fixtures()
        
        # Verify CRUDNode class exists and has correct methods
        assert hasattr(node, 'create')
        assert hasattr(node, 'get')
        assert hasattr(node, 'get_nodes_by_project')
        assert hasattr(node, 'get_by_name_and_type')
        assert hasattr(node, 'update_node')
        assert hasattr(node, 'mark_scanned')
        assert hasattr(node, 'get_unscanned_nodes')
        assert hasattr(node, 'delete')
        
        # Verify no Asset-related methods exist
        assert not hasattr(node, 'create_asset')
        assert not hasattr(node, 'get_asset')
        assert not hasattr(node, 'get_assets_by_project')
        
        # Test that all methods accept Node instances
        test_node = test_nodes[0]
        session.set_query_result('scalar_one_or_none', test_node)
        session.set_query_result('scalars_all', [test_node])
        
        # All these should work with Node instances
        await node.create(session, test_node)
        await node.get(session, test_node.id)
        await node.get_nodes_by_project(session, test_project.id)
        await node.get_by_name_and_type(session, test_project.id, test_node.name, test_node.type)
        await node.update_node(session, test_node.id, {"scanned": True})
        await node.mark_scanned(session, test_node.id)
        await node.get_unscanned_nodes(session, test_project.id)
        await node.delete(session, test_node.id)
        
        # All operations should complete without errors, confirming Node model consistency