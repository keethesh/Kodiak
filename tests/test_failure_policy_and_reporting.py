from pathlib import Path
from uuid import uuid4

from kodiak.core.failure_policy import apply_timeout_backoff
from kodiak.core.reporting import write_scan_report


def test_failure_policy_sqlmap_backoff():
    args = {"level": 5, "risk": 3, "threads": 5}
    updated, note, stop_reason = apply_timeout_backoff("sqlmap", args, timeout_count=1)
    assert stop_reason is None
    assert updated["level"] == 2
    assert updated["risk"] == 1
    assert updated["threads"] == 1
    assert "Failure policy" in (note or "")


def test_failure_policy_stop_threshold():
    args = {"threads": 40}
    updated, note, stop_reason = apply_timeout_backoff("ffuf", args, timeout_count=3)
    assert updated == args
    assert note is None
    assert "threshold" in (stop_reason or "")


def test_reporting_writes_json_and_markdown():
    report_data = {
        "scan_id": "abc123",
        "scan_name": "Scan_example",
        "target": "https://example.com",
        "status": "completed",
        "summary": {
            "agents_requested": 3,
            "agents_running": 3,
            "nodes_discovered": 10,
            "raw_findings": 5,
            "deduped_findings": 3,
            "duplicate_findings_filtered": 2,
            "duration_seconds": 42,
        },
        "findings": [{"title": "Test Finding", "severity": "high", "target": "https://example.com"}],
        "attempts": [{"tool": "nuclei", "target": "https://example.com", "status": "success", "agent_id": "a1"}],
    }

    output_dir = Path.cwd() / ".pytest-report-output" / str(uuid4())
    paths = write_scan_report(report_data, str(output_dir), "json+md")
    assert "json" in paths
    assert "markdown" in paths
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
