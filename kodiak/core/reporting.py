"""
Scan report writers for JSON and Markdown artifacts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def write_scan_report(
    report_data: Dict[str, Any],
    report_dir: str,
    report_format: str = "json+md",
) -> Dict[str, str]:
    output_dir = Path(report_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    scan_id = str(report_data.get("scan_id", "unknown"))
    written: Dict[str, str] = {}

    normalized_format = (report_format or "json+md").lower()
    write_json = normalized_format in {"json", "json+md"}
    write_md = normalized_format in {"md", "markdown", "json+md"}

    if write_json:
        json_path = output_dir / f"scan_{scan_id}.json"
        json_path.write_text(json.dumps(report_data, indent=2, default=_json_default), encoding="utf-8")
        written["json"] = str(json_path)

    if write_md:
        md_path = output_dir / f"scan_{scan_id}.md"
        md_path.write_text(_render_markdown(report_data), encoding="utf-8")
        written["markdown"] = str(md_path)

    return written


def _render_markdown(report_data: Dict[str, Any]) -> str:
    findings = report_data.get("findings", [])
    summary = report_data.get("summary", {})
    attempts = report_data.get("attempts", [])
    generated_at = datetime.now(timezone.utc).isoformat()

    lines = [
        f"# Scan Report: {report_data.get('scan_name', 'Unknown')}",
        "",
        f"- Scan ID: `{report_data.get('scan_id', 'unknown')}`",
        f"- Target: `{report_data.get('target', 'unknown')}`",
        f"- Status: `{report_data.get('status', 'unknown')}`",
        f"- Generated At (UTC): `{generated_at}`",
        "",
        "## Summary",
        "",
        f"- Agents: requested={summary.get('agents_requested', 0)}, running={summary.get('agents_running', 0)}",
        f"- Nodes discovered: {summary.get('nodes_discovered', 0)}",
        f"- Findings: unique={summary.get('deduped_findings', 0)} raw={summary.get('raw_findings', 0)}",
        f"- Duplicate findings filtered: {summary.get('duplicate_findings_filtered', 0)}",
        f"- Duration seconds: {summary.get('duration_seconds', summary.get('duration', 0))}",
        "",
        "## Findings",
        "",
    ]

    if not findings:
        lines.append("- No findings captured.")
    else:
        for finding in findings[:50]:
            lines.append(
                f"- [{str(finding.get('severity', 'info')).upper()}] "
                f"{finding.get('title', 'Untitled')} ({finding.get('target', '-')})"
            )

    lines.extend(["", "## Tool Attempts", ""])
    if not attempts:
        lines.append("- No attempt records captured.")
    else:
        for attempt in attempts[:80]:
            lines.append(
                f"- {attempt.get('tool', 'unknown')} target={attempt.get('target', '-')} "
                f"status={attempt.get('status', 'unknown')} agent={attempt.get('agent_id', '-')}"
            )

    return "\n".join(lines) + "\n"


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)
