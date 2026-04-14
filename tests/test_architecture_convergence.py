"""
Tests for Phase 1-4 architecture changes:
- WorkUnit single-scope schema
- Schema validation and migration
- Tool preflight and availability
- Reporting alignment
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from kodiak.core.tool_availability import (
    ToolAvailability,
    check_tool_availability,
    filter_available_tools,
    filter_unavailable_tools,
    get_default_tools_to_check,
)
from kodiak.database.engine import SchemaMigrationRequired, _validate_sqlite_schema


class TestToolAvailability:
    """Tests for tool availability checking."""

    def test_tool_availability_initialization(self):
        """Test ToolAvailability dataclass initialization."""
        availability = ToolAvailability(
            available_tools={"nmap", "nuclei"},
            unavailable_tools={"nikto"},
        )
        
        assert availability.is_available("nmap")
        assert availability.is_available("nuclei")
        assert availability.is_unavailable("nikto")
        assert not availability.is_available("wpscan")

    def test_tool_availability_default_unchecked(self):
        """Test that unchecked availability returns True for is_available."""
        availability = ToolAvailability()
        
        assert availability.is_available("any_tool")
        assert not availability.is_unavailable("any_tool")
        assert not availability.is_checked()

    def test_get_unavailable_summary(self):
        """Test unavailable tools summary."""
        availability = ToolAvailability(
            unavailable_tools={"nikto", "wpscan"},
        )
        
        summary = availability.get_unavailable_summary()
        assert "nikto" in summary
        assert "wpscan" in summary
        assert summary["nikto"] == "not found in Docker container"

    def test_filter_available_tools(self):
        """Test filtering tools by availability."""
        availability = ToolAvailability(
            available_tools={"nmap", "nuclei", "ffuf"},
        )
        
        tools = {"nmap", "nikto", "ffuf", "wpscan"}
        filtered = filter_available_tools(tools, availability)
        
        assert filtered == {"nmap", "ffuf"}
        assert "nikto" not in filtered
        assert "wpscan" not in filtered

    def test_filter_unavailable_tools(self):
        """Test filtering tools by unavailability."""
        availability = ToolAvailability(
            unavailable_tools={"nikto", "wpscan"},
        )
        
        tools = {"nmap", "nikto", "ffuf", "wpscan"}
        filtered = filter_unavailable_tools(tools, availability)
        
        assert filtered == {"nikto", "wpscan"}
        assert "nmap" not in filtered

    def test_get_default_tools_to_check(self):
        """Test that default tools includes heavy tools."""
        tools = get_default_tools_to_check()
        
        assert "nuclei" in tools
        assert "nmap" in tools
        assert "ffuf" in tools
        assert "sqlmap" in tools


class TestSchemaValidation:
    """Tests for schema validation."""

    @pytest.mark.asyncio
    async def test_legacy_schema_raises_migration_required(self):
        """Legacy schema with targets_json should raise SchemaMigrationRequired."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (1, "id"), (2, "scan_id"), (3, "targets_json"), (4, "targets_hash"),
        ]
        mock_conn.execute.return_value = mock_result
        
        with pytest.raises(SchemaMigrationRequired) as exc_info:
            await _validate_sqlite_schema(mock_conn)
        
        assert "targets_json" in str(exc_info.value)
        assert "--reset" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_new_schema_passes_validation(self):
        """New schema without targets_json should pass."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (1, "id"), (2, "scan_id"), (3, "target"), (4, "scope_key"),
            (5, "tool_family"), (6, "target_kind"),
        ]
        mock_conn.execute.return_value = mock_result
        
        await _validate_sqlite_schema(mock_conn)

    @pytest.mark.asyncio
    async def test_missing_columns_raises_migration_required(self):
        """Missing required columns should raise SchemaMigrationRequired."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (1, "id"), (2, "scan_id"),
        ]
        mock_conn.execute.return_value = mock_result
        
        with pytest.raises(SchemaMigrationRequired) as exc_info:
            await _validate_sqlite_schema(mock_conn)
        
        assert "target" in str(exc_info.value) or "scope_key" in str(exc_info.value)


class TestScanResult:
    """Tests for ScanResult with asset_count."""

    def test_scan_result_asset_count(self):
        """Test that ScanResult includes asset_count."""
        from kodiak.core.scan_runner import ScanResult
        
        result = ScanResult(
            status="completed",
            summary="Test scan",
            nodes_discovered=10,
            asset_count=15,
            findings_count=5,
        )
        
        assert result.nodes_discovered == 10
        assert result.asset_count == 15
        assert result.findings_count == 5


class TestPlannerToolGating:
    """Tests for planner tool availability gating."""

    def test_planner_skips_unavailable_tools(self):
        """Test that planner skips rules for unavailable tools."""
        from kodiak.core.planner import PlannerAgent
        
        availability = ToolAvailability(
            available_tools={"httpx", "nmap"},
            unavailable_tools={"nuclei", "nikto"},
        )
        
        planner = PlannerAgent.__new__(PlannerAgent)
        planner._tool_availability = availability
        
        assert planner._is_tool_available("httpx")
        assert planner._is_tool_available("nmap")
        assert not planner._is_tool_available("nuclei")
        assert not planner._is_tool_available("nikto")

    def test_skip_unavailable_tool_returns_true_for_missing_tools(self):
        """Test that _skip_unavailable_tool returns True for unavailable."""
        from kodiak.core.planner import PlannerAgent
        
        availability = ToolAvailability(
            unavailable_tools={"nuclei"},
        )
        
        planner = PlannerAgent.__new__(PlannerAgent)
        planner._tool_availability = availability
        
        assert planner._skip_unavailable_tool("nuclei")
        assert not planner._skip_unavailable_tool("nmap")

    def test_no_tool_availability_means_available(self):
        """Test that with no availability info, tools are available."""
        from kodiak.core.planner import PlannerAgent
        
        planner = PlannerAgent.__new__(PlannerAgent)
        planner._tool_availability = None
        
        assert planner._is_tool_available("any_tool")
        assert not planner._skip_unavailable_tool("any_tool")


class TestReportingAlignment:
    """Tests for reporting with kernel assets."""

    def test_markdown_report_uses_asset_count(self):
        """Test that markdown report uses asset_count."""
        from kodiak.core.reporting import _render_markdown
        
        report_data = {
            "scan_name": "Test Scan",
            "scan_id": "123",
            "target": "https://example.com",
            "status": "completed",
            "summary": {
                "asset_count": 15,
                "nodes_discovered": 10,
                "deduped_findings": 5,
                "raw_findings": 7,
            },
            "findings": [],
            "attempts": [],
        }
        
        md = _render_markdown(report_data)
        
        assert "Assets discovered: 15" in md
        assert "Findings: unique=5" in md

    def test_markdown_report_work_queue(self):
        """Test that markdown report shows work queue counts."""
        from kodiak.core.reporting import _render_markdown
        
        report_data = {
            "scan_name": "Test Scan",
            "scan_id": "123",
            "target": "https://example.com",
            "status": "completed",
            "summary": {
                "asset_count": 10,
                "work_pending": 5,
                "work_completed": 20,
            },
            "findings": [],
            "attempts": [],
        }
        
        md = _render_markdown(report_data)
        
        assert "pending=5" in md
        assert "completed=20" in md
