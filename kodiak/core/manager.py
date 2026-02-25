"""
Manager Agent — single LLM brain using structured output for Kodiak scans.

Architecture (structured output, no function calling):
  1. LLM returns a JSON `KodiakResponse` with commands[], findings[], notes[], etc.
  2. Commands are executed in parallel via Docker (bash -c).
  3. Findings and notes are persisted to the database by the orchestrator.
  4. Scan state is updated from the LLM's `discoveries` field.
  5. Phase advancement and scan completion are driven by `phase_action`.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger

from kodiak.api.events import TUIEventManager
from kodiak.core.config import settings
from kodiak.core.response_schema import (
    ActionType,
    KodiakResponse,
    PhaseAction,
)
from kodiak.core.scheduler import EventDrivenScheduler, SchedulerEvent
from kodiak.core.scan_state import ScanPhase, ScanState
from kodiak.core.tools.inventory import ToolInventory
from kodiak.core.worker import CommandResult, CommandTask, dispatch_commands
from kodiak.database import crud
from kodiak.database.models import Attempt, EngagementNote, Finding, NoteCategory, FindingSeverity
from kodiak.services import llm
from kodiak.services.gemini_client import GeminiClient, GeminiResponse


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ManagerResult:
    """Outcome of a Manager-driven scan."""
    status: str  # completed | max_iterations | failed | cancelled
    summary: str
    findings_count: int
    iterations: int


# ---------------------------------------------------------------------------
# Manager Agent
# ---------------------------------------------------------------------------

class ManagerAgent:
    """
    Single-brain orchestrator for a penetration-testing scan.

    Uses structured output (no function calling):
      think    → LLM returns KodiakResponse JSON (commands, findings, notes, phase_action)
      execute  → run commands in parallel via Docker
      observe  → update ScanState from discoveries + command results
      persist  → write findings/notes/attempts to DB
      repeat   → until phase_action=complete or budget exhausted
    """

    def __init__(
        self,
        event_manager: TUIEventManager,
        tool_inventory: ToolInventory,
    ):
        self.event_manager = event_manager
        self.tool_inventory = tool_inventory
        self._gemini = GeminiClient()
        self.scan_state: Optional[ScanState] = None
        self._prior_knowledge: str = ""

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(
        self,
        target: str,
        instructions: str,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        max_iterations: int = 30,
        allowed_tools: Optional[List[str]] = None,
        event_scheduler: Optional[bool] = None,
    ) -> ManagerResult:
        """Execute the full scan lifecycle."""

        logger.info(f"🚀 Manager starting scan against {target}")
        self.scan_state = ScanState(target=target)
        self.scan_state.ensure_target(target)

        scan_id_str = str(scan_id)

        # Load prior engagement knowledge for this project
        self._prior_knowledge, _pk_notes, _pk_findings = await self._load_prior_knowledge(
            session, project_id
        )
        if (_pk_notes > 0 or _pk_findings > 0) and self.event_manager:
            try:
                await self.event_manager.emit_prior_knowledge_loaded(
                    notes_count=_pk_notes,
                    findings_count=_pk_findings,
                    scan_id=scan_id_str,
                )
            except Exception:
                pass

        history: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    "<scan_request>\n"
                    f"<target>{target}</target>\n"
                    f"<instructions>{instructions or 'Conduct a comprehensive security assessment.'}</instructions>\n"
                    "</scan_request>"
                ),
            }
        ]

        event_mode = settings.event_scheduler_enabled if event_scheduler is None else bool(event_scheduler)

        if event_mode:
            return await self._run_event_mode(
                history=history,
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                scan_id_str=scan_id_str,
                max_iterations=max_iterations,
                allowed_tools=allowed_tools,
            )

        return await self._run_batch_mode(
            history=history,
            session=session,
            project_id=project_id,
            scan_id=scan_id,
            scan_id_str=scan_id_str,
            max_iterations=max_iterations,
            allowed_tools=allowed_tools,
        )

    async def _run_batch_mode(
        self,
        *,
        history: List[Dict[str, Any]],
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        scan_id_str: str,
        max_iterations: int,
        allowed_tools: Optional[List[str]],
    ) -> ManagerResult:
        min_iterations = min(max_iterations, max(3, int(max_iterations * 0.15)))

        for iteration in range(1, max_iterations + 1):
            logger.debug(f"🔄 Manager iteration {iteration}/{max_iterations}")
            self._append_iteration_warnings(history, iteration, max_iterations)

            response = await self._think(history, iteration, scan_id_str)

            if response is None:
                history.append({"role": "assistant", "content": '{"analysis":"Error: empty response","commands":[],"actions":[],"phase_action":"continue"}'})
                history.append({
                    "role": "user",
                    "content": "<retry>Previous call failed. Output valid JSON with commands/actions.</retry>",
                })
                continue

            if response.content:
                logger.debug(f"LLM Raw Response:\n{response.content}")

            kodiak_resp = self._parse_kodiak_response(response.content)
            await self._emit_thought(kodiak_resp.analysis if kodiak_resp else response.content, scan_id_str)

            if kodiak_resp is None:
                history.append({"role": "assistant", "content": response.content or ""})
                history.append({
                    "role": "user",
                    "content": (
                        "<retry>Your response was not valid JSON matching the schema. "
                        "Output JSON with: analysis, commands[], actions[], discoveries, "
                        "findings[], notes[], phase_action.</retry>"
                    ),
                })
                continue

            history.append({"role": "assistant", "content": response.content})
            self._apply_discoveries(kodiak_resp)
            await self._persist_response_findings_notes(kodiak_resp, session, project_id, scan_id)

            launch_tasks, _, resolved_phase_action = self._extract_runtime_actions(
                kodiak_resp=kodiak_resp,
                allowed_tools=allowed_tools,
            )

            completion_attempted = resolved_phase_action == PhaseAction.COMPLETE
            if completion_attempted:
                if iteration < min_iterations:
                    history.append({
                        "role": "user",
                        "content": (
                            f"<completion_rejected>You attempted to complete at iteration {iteration} "
                            f"but minimum is {min_iterations}. Continue scanning.</completion_rejected>"
                        ),
                    })
                    continue

                summary = kodiak_resp.scan_summary or "Scan completed"
                if self.scan_state.phase != ScanPhase.REPORTING:
                    while self.scan_state.phase != ScanPhase.REPORTING:
                        self.scan_state.advance_phase()
                await self._persist_final_findings(session, project_id, scan_id)
                return ManagerResult(
                    status="completed",
                    summary=summary,
                    findings_count=self.scan_state.findings_count,
                    iterations=iteration,
                )

            if resolved_phase_action == PhaseAction.ADVANCE:
                await self._advance_phase(scan_id_str)

            if launch_tasks:
                results = await dispatch_commands(
                    commands=launch_tasks,
                    event_manager=self.event_manager,
                    scan_id=scan_id_str,
                    global_concurrency=settings.global_tool_concurrency,
                )
                for cr in results:
                    await self._persist_command_attempt(session, project_id, scan_id, cr)
                    self._record_command_result_to_scan_state(cr)
                history.append({"role": "user", "content": self._format_command_results(results)})
            else:
                history.append({
                    "role": "user",
                    "content": (
                        "<next_step>No commands were dispatched. Output commands/actions to continue "
                        "the scan, or set phase_action to 'complete' with scan_summary.</next_step>"
                    ),
                })

            history = self._trim_history(history, max_turns=80)

        await self._persist_final_findings(session, project_id, scan_id)
        return ManagerResult(
            status="max_iterations",
            summary=f"Reached iteration budget ({max_iterations})",
            findings_count=self.scan_state.findings_count,
            iterations=max_iterations,
        )

    async def _run_event_mode(
        self,
        *,
        history: List[Dict[str, Any]],
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        scan_id_str: str,
        max_iterations: int,
        allowed_tools: Optional[List[str]],
    ) -> ManagerResult:
        scheduler = EventDrivenScheduler(
            global_concurrency=settings.global_tool_concurrency,
            event_manager=self.event_manager,
            scan_id=scan_id_str,
        )
        llm_calls = 0
        need_replan = True
        heartbeat_seconds = max(5, int(settings.event_scheduler_heartbeat_seconds))
        cooldown_seconds = max(1, int(settings.event_scheduler_replan_cooldown_seconds))
        last_replan_mono = 0.0
        min_iterations = min(max_iterations, max(3, int(max_iterations * 0.15)))

        try:
            while llm_calls < max_iterations:
                if need_replan:
                    iteration = llm_calls + 1
                    logger.debug(f"🧠 Event replan {iteration}/{max_iterations}")
                    self._append_iteration_warnings(history, iteration, max_iterations)

                    response = await self._think(history, iteration, scan_id_str)
                    llm_calls += 1
                    self.scan_state.mark_replan()
                    last_replan_mono = time.monotonic()

                    if response is None:
                        history.append({"role": "assistant", "content": '{"analysis":"Error: empty response","commands":[],"actions":[],"phase_action":"continue"}'})
                        history.append({
                            "role": "user",
                            "content": "<retry>Previous call failed. Output valid JSON with commands/actions.</retry>",
                        })
                        need_replan = True
                        continue

                    if response.content:
                        logger.debug(f"LLM Raw Response:\n{response.content}")

                    kodiak_resp = self._parse_kodiak_response(response.content)
                    await self._emit_thought(kodiak_resp.analysis if kodiak_resp else response.content, scan_id_str)

                    if kodiak_resp is None:
                        history.append({"role": "assistant", "content": response.content or ""})
                        history.append({
                            "role": "user",
                            "content": (
                                "<retry>Your response was not valid JSON matching the schema. "
                                "Output JSON with: analysis, commands[], actions[], discoveries, "
                                "findings[], notes[], phase_action.</retry>"
                            ),
                        })
                        need_replan = True
                        continue

                    history.append({"role": "assistant", "content": response.content})
                    self._apply_discoveries(kodiak_resp)
                    await self._persist_response_findings_notes(kodiak_resp, session, project_id, scan_id)

                    write_tasks, launch_tasks, cancel_task_ids, resolved_phase_action = self._extract_runtime_actions(
                        kodiak_resp=kodiak_resp,
                        allowed_tools=allowed_tools,
                    )

                    # Execute write_file actions synchronously first to avoid race conditions
                    if write_tasks:
                        from kodiak.core.worker import dispatch_commands
                        write_results = await dispatch_commands(
                            write_tasks,
                            event_manager=self.event_manager,
                            scan_id=scan_id_str,
                            global_concurrency=4,
                        )
                        for res in write_results:
                            await self._persist_command_attempt(session, project_id, scan_id, res)
                            self._record_command_result_to_scan_state(res)
                            # Let the LLM know the file was written
                            history.append({"role": "user", "content": self._format_command_results([res])})



                    for cancel_id in cancel_task_ids:
                        await scheduler.cancel(cancel_id)

                    max_queue = max(1, int(settings.event_scheduler_max_queue))
                    dropped_for_queue = 0
                    for task in launch_tasks:
                        if scheduler.pending_count + scheduler.running_count >= max_queue:
                            dropped_for_queue += 1
                            continue
                        accepted = await scheduler.submit(task)
                        if accepted:
                            self.scan_state.queue_task(
                                task_id=task.task_id,
                                tool=self._tool_from_command(task.command),
                                command=task.command,
                            )

                    if dropped_for_queue:
                        history.append({
                            "role": "user",
                            "content": (
                                f"<queue_guard>Dropped {dropped_for_queue} launch action(s) "
                                f"because scheduler queue cap is {max_queue}.</queue_guard>"
                            ),
                        })

                    if resolved_phase_action == PhaseAction.ADVANCE:
                        advanced = await self._advance_phase(scan_id_str, scheduler)
                        if not advanced:
                            history.append({
                                "role": "user",
                                "content": (
                                    "<phase_advance_deferred>Phase advance requested but deferred "
                                    "because critical recon tasks are still running.</phase_advance_deferred>"
                                ),
                            })

                    if resolved_phase_action == PhaseAction.COMPLETE:
                        if iteration < min_iterations:
                            history.append({
                                "role": "user",
                                "content": (
                                    f"<completion_rejected>You attempted to complete at iteration {iteration} "
                                    f"but minimum is {min_iterations}. Continue scanning.</completion_rejected>"
                                ),
                            })
                            need_replan = True
                            continue

                        if scheduler.has_inflight():
                            history.append({
                                "role": "user",
                                "content": (
                                    "<completion_deferred>Completion requested while tasks are still running. "
                                    "Wait for in-flight command results, then reassess completion.</completion_deferred>"
                                ),
                            })
                            need_replan = False
                            continue

                        summary = kodiak_resp.scan_summary or "Scan completed"
                        if self.scan_state.phase != ScanPhase.REPORTING:
                            while self.scan_state.phase != ScanPhase.REPORTING:
                                self.scan_state.advance_phase()
                        await self._persist_final_findings(session, project_id, scan_id)
                        return ManagerResult(
                            status="completed",
                            summary=summary,
                            findings_count=self.scan_state.findings_count,
                            iterations=llm_calls,
                        )

                    if not scheduler.has_inflight():
                        history.append({
                            "role": "user",
                            "content": (
                                "<next_step>No in-flight commands. Output launch/cancel/wait actions "
                                "or commands to continue scanning.</next_step>"
                            ),
                        })
                        need_replan = True
                    else:
                        need_replan = False

                    history = self._trim_history(history, max_turns=80)
                    continue

                event = await scheduler.next_event(timeout_seconds=heartbeat_seconds)
                if event is None:
                    history.append({
                        "role": "user",
                        "content": (
                            f"<heartbeat>{heartbeat_seconds}s elapsed without decisive scheduler signal. "
                            "Replan using current active task state.</heartbeat>"
                        ),
                    })
                    need_replan = True
                    history = self._trim_history(history, max_turns=80)
                    continue

                self._apply_scheduler_event_to_scan_state(event)

                if event.result:
                    await self._persist_command_attempt(session, project_id, scan_id, event.result)
                    self._record_command_result_to_scan_state(event.result)
                    history.append({"role": "user", "content": self._format_command_results([event.result])})
                else:
                    history.append({
                        "role": "user",
                        "content": (
                            f"<scheduler_event type=\"{event.event_type}\" task_id=\"{event.task_id}\" "
                            f"status=\"{event.status}\">{event.command[:220]}</scheduler_event>"
                        ),
                    })

                now_mono = time.monotonic()
                if self._should_replan_on_scheduler_event(
                    event=event,
                    scheduler=scheduler,
                    now_mono=now_mono,
                    last_replan_mono=last_replan_mono,
                    cooldown_seconds=cooldown_seconds,
                ):
                    need_replan = True
                else:
                    need_replan = False

                history = self._trim_history(history, max_turns=80)

            await scheduler.cancel_all()
            await self._persist_final_findings(session, project_id, scan_id)
            return ManagerResult(
                status="max_iterations",
                summary=f"Reached iteration budget ({max_iterations})",
                findings_count=self.scan_state.findings_count,
                iterations=llm_calls,
            )
        finally:
            await scheduler.cancel_all()

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _think(
        self,
        history: List[Dict[str, Any]],
        iteration: int,
        scan_id: str,
    ) -> Optional[GeminiResponse]:
        """Single LLM call: system prompt + history → structured KodiakResponse JSON."""

        system_prompt = self._build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]

        # Ensure first non-system message is user (Gemini requirement)
        trimmed = [m for m in history if m.get("role") != "system"]
        if trimmed and trimmed[0].get("role") != "user":
            trimmed.insert(0, {"role": "user", "content": "Begin scan."})
        messages.extend(trimmed)

        try:
            normalized_model = llm.normalize_model_name(settings.llm_model)
            thinking_level = llm.resolve_gemini_thinking_level(
                normalized_model, settings.gemini_thinking_level
            )
            api_key = llm.get_google_api_key()

            if self.event_manager:
                try:
                    await self.event_manager.emit_agent_thinking(
                        agent_id="manager",
                        message=f"Iteration {iteration}",
                        scan_id=scan_id,
                    )
                except Exception:
                    pass

            response = await self._gemini.generate(
                model=normalized_model,
                api_key=api_key,
                system_prompt=system_prompt,
                messages=messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                thinking_level=thinking_level,
                response_schema=KodiakResponse,
            )
            return response if response else None
        except Exception as exc:
            logger.error(f"Manager think() failed: {exc}")
            return None

    def _append_iteration_warnings(
        self,
        history: List[Dict[str, Any]],
        iteration: int,
        max_iterations: int,
    ) -> None:
        if max_iterations > 10 and iteration == int(max_iterations * 0.85):
            remaining = max_iterations - iteration
            history.append({
                "role": "user",
                "content": (
                    f"<iteration_warning>Iteration {iteration}/{max_iterations}. "
                    f"{remaining} remaining. Prioritise completion.</iteration_warning>"
                ),
            })
        elif iteration == max_iterations - 2:
            history.append({
                "role": "user",
                "content": (
                    "<final_warning>Only 2 iterations remain. "
                    "Set phase_action to 'complete' with a scan_summary NOW.</final_warning>"
                ),
            })

    async def _emit_thought(self, thought_text: str, scan_id: str) -> None:
        if not self.event_manager or not thought_text:
            return
        try:
            await self.event_manager.emit_agent_thought(
                agent_id="manager",
                thought=thought_text,
                scan_id=scan_id,
            )
        except Exception:
            pass

    async def _persist_response_findings_notes(
        self,
        resp: KodiakResponse,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> None:
        for finding in resp.findings:
            await self._persist_finding(finding, session, project_id, scan_id)
        for note in resp.notes:
            await self._persist_note(note, session, project_id, scan_id)

    def _extract_runtime_actions(
        self,
        *,
        kodiak_resp: KodiakResponse,
        allowed_tools: Optional[List[str]],
    ) -> tuple[List[CommandTask], List[CommandTask], List[str], PhaseAction]:
        write_tasks: List[CommandTask] = []
        launch_tasks: List[CommandTask] = []
        cancel_task_ids: List[str] = []
        phase_action = kodiak_resp.phase_action

        for action in kodiak_resp.actions:
            if action.type == ActionType.LAUNCH and action.command.strip():
                launch_tasks.append(
                    CommandTask(
                        command=action.command.strip(),
                        rationale=action.rationale or "Action-driven launch",
                        timeout=max(1, int(action.timeout or 300)),
                    )
                )
            elif action.type == ActionType.CANCEL and action.task_id.strip():
                cancel_task_ids.append(action.task_id.strip())
            elif action.type == ActionType.ADVANCE:
                phase_action = PhaseAction.ADVANCE
            elif action.type == ActionType.COMPLETE:
                phase_action = PhaseAction.COMPLETE
            elif action.type == ActionType.WRITE_FILE and action.target_path.strip() and action.content:
                import base64
                import shlex
                b64_content = base64.b64encode(action.content.encode("utf-8")).decode("utf-8")
                target_path = shlex.quote(action.target_path.strip())
                bash_cmd = f"echo {b64_content} | base64 -d > {target_path}"
                write_tasks.append(
                    CommandTask(
                        command=bash_cmd,
                        rationale=action.rationale or f"Write file to {target_path}",
                        timeout=max(1, int(action.timeout or 30)),
                    )
                )

        for cmd in kodiak_resp.commands:
            launch_tasks.append(
                CommandTask(
                    command=cmd.command,
                    rationale=cmd.rationale,
                    timeout=cmd.timeout,
                )
            )

        allowed = set(allowed_tools or [])
        from kodiak.core.tools.registry import get_gated_tool_names
        gated_tool_names = get_gated_tool_names()
        
        filtered_write: List[CommandTask] = []
        filtered_launch: List[CommandTask] = []
        seen_commands: set[str] = set()
        
        for tasks, filtered_list in [(write_tasks, filtered_write), (launch_tasks, filtered_launch)]:
            for task in tasks:
                normalized = task.command.strip()
                if not normalized or normalized in seen_commands:
                    continue
                tool = self._tool_from_command(normalized)
                if allowed_tools and tool in gated_tool_names and tool not in allowed:
                    logger.debug(f"Skipping disallowed tool command: {tool} -> {normalized[:120]}")
                    continue
                seen_commands.add(normalized)
                filtered_list.append(task)

        unique_cancel_ids = list(dict.fromkeys(cancel_task_ids))
        return filtered_write, filtered_launch, unique_cancel_ids, phase_action


    async def _advance_phase(self, scan_id_str: str, scheduler=None) -> bool:
        if self.scan_state.phase == ScanPhase.RECON and scheduler:
            recon_tools = {"nmap", "subfinder", "dig", "whois", "whatweb", "httpx"}
            running_recon = [
                tid for tid, state in (scheduler.snapshot_states() or {}).items()
                if state == "running" and any(
                    t in self.scan_state.active_tasks.get(tid, __import__("kodiak.core.scan_state", fromlist=["TaskRecord"]).TaskRecord("", "", "", "")).command
                    for t in recon_tools
                )
            ]
            if running_recon:
                logger.info(f"⏸️ Phase advance deferred: {len(running_recon)} recon tasks still running")
                return False

        old_phase = self.scan_state.phase.value
        advanced = self.scan_state.advance_phase()
        if not advanced:
            return False
        new_phase = self.scan_state.phase.value
        logger.info(f"📍 Phase advanced: {old_phase} → {new_phase}")
        if self.event_manager:
            try:
                await self.event_manager.emit_phase_advanced(
                    old_phase=old_phase,
                    new_phase=new_phase,
                    scan_id=scan_id_str,
                )
            except Exception:
                pass
        return True

    @staticmethod
    def _tool_from_command(command: str) -> str:
        return command.split()[0] if command.strip() else "cmd"

    def _record_command_result_to_scan_state(self, result: CommandResult) -> None:
        tool = self._tool_from_command(result.command)
        target = self._extract_target_from_command(result.command)
        if result.timed_out:
            status = "timeout"
        elif result.exit_code == 0:
            status = "success"
        else:
            status = "error"

        signal = (result.stdout or result.stderr or "").strip()
        summary = signal[:240] if signal else f"exit_code={result.exit_code}"
        self.scan_state.record_tool_result(
            tool=tool,
            target=target,
            status=status,
            summary=summary,
        )

    @staticmethod
    def _extract_target_from_command(command: str) -> str:
        url_match = re.search(r'https?://[^\s\'"]+', command)
        if url_match:
            return url_match.group(0)
        host_match = re.search(r'-[duh]\s+([^\s]+)', command)
        if host_match:
            return host_match.group(1)
        return "unknown"

    def _apply_scheduler_event_to_scan_state(self, event: SchedulerEvent) -> None:
        if event.event_type == "task_started":
            self.scan_state.start_task(event.task_id)
            return
        if event.event_type == "task_queued":
            if event.task_id not in self.scan_state.active_tasks:
                self.scan_state.queue_task(
                    task_id=event.task_id,
                    tool=event.tool,
                    command=event.command,
                )
            return
        if event.event_type == "task_completed":
            self.scan_state.finish_task(event.task_id, "success")
            return
        if event.event_type == "task_timeout":
            self.scan_state.finish_task(event.task_id, "timeout")
            return
        if event.event_type == "task_failed":
            self.scan_state.finish_task(event.task_id, "failed")
            return
        if event.event_type == "task_cancelled":
            self.scan_state.finish_task(event.task_id, "cancelled")

    def _should_replan_on_scheduler_event(
        self,
        *,
        event: SchedulerEvent,
        scheduler: EventDrivenScheduler,
        now_mono: float,
        last_replan_mono: float,
        cooldown_seconds: int,
    ) -> bool:
        if not scheduler.has_inflight():
            return True

        in_cooldown = (now_mono - last_replan_mono) < cooldown_seconds

        if event.event_type in {"task_timeout", "task_failed", "task_cancelled"}:
            return True

        if event.event_type == "task_completed":
            if self._is_high_signal_result(event.result):
                return True
            if in_cooldown:
                return False
            # If we have spare capacity and no queue, replan for fresh launches.
            if scheduler.pending_count == 0 and scheduler.running_count < settings.global_tool_concurrency:
                return True

        return False

    @staticmethod
    def _is_high_signal_result(result: Optional[CommandResult]) -> bool:
        if not result:
            return False
        corpus = f"{result.stdout}\n{result.stderr}".lower()
        indicators = [
            "vulnerable",
            "sql injection",
            "xss",
            "rce",
            "command injection",
            "authentication bypass",
            "admin panel",
            "directory listing",
            "credential",
            "password",
            "token",
            "lfi",
            "ssrf",
        ]
        return any(indicator in corpus for indicator in indicators)

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """
        Construct the Manager's system prompt optimized for Gemini 3:
        - Concise, direct instructions (Gemini 3 over-analyses verbose prompts)
        - XML-tagged sections for clear structure
        - Tool catalog described as text (no function declarations)
        - Context (scan state) placed before the task
        - Task anchored at the very end
        """
        assert self.scan_state is not None

        phase = self.scan_state.phase

        phase_objectives = {
            ScanPhase.RECON: (
                "Discover the full attack surface: subdomains, open ports, "
                "and technology fingerprints. Dispatch multiple recon commands in parallel."
            ),
            ScanPhase.ENUMERATION: (
                "Map services on live hosts: probe HTTP endpoints, crawl for URLs, "
                "fuzz for hidden directories. Prioritize hosts with exposed web services. "
                "Focus on subdomains that suggest dev/staging/admin environments."
            ),
            ScanPhase.VULN_SCAN: (
                "Identify exploitable vulnerabilities: run nuclei templates, "
                "test for injection points, check for known CVEs matching discovered versions."
            ),
            ScanPhase.EXPLOITATION: (
                "Confirm and exploit vulnerabilities: run sqlmap/commix on injection points, "
                "gather proof-of-concept evidence, extract data where possible."
            ),
            ScanPhase.REPORTING: (
                "Compile all findings. Set phase_action='complete' with a comprehensive "
                "scan_summary covering all discovered vulnerabilities."
            ),
        }

        sections = [
            "<role>",
            "You are KODIAK, an elite autonomous penetration tester. You are relentless, thorough, and persistent.",
            "You do NOT stop early. You do NOT declare a target 'secure' without exhausting every applicable technique.",
            "Every parameter is a potential injection point. Every subdomain gets scanned. Every exposed service is a finding.",
            "Surface-level scans find nothing — real vulnerabilities are buried deep. Dig until you hit them.",
            "One confirmed critical finding outweighs a hundred informational flags. Prioritize exploitable impact over volume.",
            "When automated tools come up empty, that is a signal to shift tactics, not to stop.",
            f"Current date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. Knowledge cutoff: January 2025.",
            "</role>",
            "",
            "<high_value_targets>",
            "Actively hunt for these vulnerability classes across every discovered endpoint:",
            "- IDOR: modify object references (IDs, UUIDs, filenames) in every authenticated request.",
            "- SQLi: test all user-controllable parameters — GET, POST, headers, cookies — with error-based, blind, and time-based payloads.",
            "- SSRF: probe any parameter that accepts URLs or hostnames for internal network access and cloud metadata (169.254.169.254).",
            "- XSS: inject into reflected, stored, and DOM contexts. Attempt attribute breakout and event-handler injection.",
            "- XXE: submit crafted XML to any endpoint that parses it. Test for file disclosure and out-of-band exfiltration.",
            "- RCE: check deserialization endpoints, template injection points, and file upload handlers.",
            "- CSRF: verify state-changing actions enforce origin validation and anti-CSRF tokens.",
            "- Race conditions: send concurrent identical requests to financial or state-changing endpoints.",
            "- Business logic: test workflow sequences out of order, manipulate pricing/quantity fields, bypass multi-step processes.",
            "- Auth/JWT: test for algorithm confusion (none/HS256→RS256), weak secrets, token reuse, and privilege escalation via role claims.",
            "Escalate from basic to advanced techniques. When standard payloads fail, craft targeted bypasses.",
            "Chain low-severity issues into high-impact attack paths — a leaked API key + an unprotected admin endpoint = critical.",
            "</high_value_targets>",
            "",
            "<instructions>",
            "For each iteration, reason through these steps:",
            "1. ANALYZE: Review scan state and previous command results. What is known? What is unknown?",
            "2. CORRELATE: Connect findings across commands — a version string suggests specific CVEs,",
            "   an exposed .git means source code review, an error message leaks internal paths.",
            "   Think in ATTACK CHAINS: if X is exposed AND Y is also exposed, what does that mean together?",
            "   Example: Umbraco + IIS + exposed installer = potential RCE chain. phpMyAdmin + cPanel = credential reuse.",
            "   Pivot across targets: credentials, API keys, or backup files found on one subdomain",
            "   MUST be tested against login portals and APIs discovered on other subdomains.",
            "3. PRIORITIZE: Rank targets by attack surface. Focus on what's most likely exploitable.",
            "4. ACT: Output runtime actions using `actions[]` (preferred) and/or `commands[]` (legacy).",
            "   Use `launch` to run commands, `cancel` to stop low-value running tasks,",
            "   `write_file` to safely write exploit scripts/payloads to the sandbox (avoids bash escaping hell),",
            "   `wait` to defer, `advance` to move phase, `complete` when done.",
            "   For every launch/cancel/write_file action, explain your rationale.",
            "   Be CREATIVE over repetitive: try one well-crafted payload per technique class",
            "   (reflected, stored, DOM-based, attribute breakout, event handler) rather than brute-forcing the same vector.",
            "5. ADAPT: If a command fails or a WAF blocks you, change approach entirely.",
            "   Try different encoding, flags, alternative tools, or creative workarounds.",
            "   Do not repeat the same failed command — diagnose WHY it failed and fix it.",
            "   When a payload is blocked, mutate it: alternate encodings (URL, Unicode, Base64, double-encoding),",
            "   comment injection, chunked transfer, or HTTP method/version swaps.",
            "6. PERSIST: Never declare a target 'secure' or 'clean' without exhaustive testing.",
            "   If a tool finds nothing, that is not a dead end — try a different tool, technique, or angle.",
            "   Absence of a finding is not evidence of security.",
            "",
            "If <prior_knowledge> is present, treat attack_hint targets as highest priority.",
            "Known hosts with attack_hints often have sibling vulnerabilities.",
            "</instructions>",
            "",
            "<constraints>",
            "- Output MULTIPLE commands per iteration — they run concurrently.",
            "- Never repeat a command with identical arguments.",
            "- Prefer `actions[]` over `commands[]` for event-driven orchestration.",
            "- If a task is clearly low-value and better leads exist, emit a `cancel` action.",
            "- Timed-out commands: retry once with reduced scope. If it times out again, record a dead_end note.",
            "- Failed commands (non-zero exit, NOT timeout): diagnose the error message, fix the syntax/flags, and retry.",
            "  Do NOT ignore failed commands — they often indicate a misconfigured flag or quoting issue.",
            "- Phase order: RECON → ENUMERATION → VULN_SCAN → EXPLOITATION → REPORTING.",
            "  Set phase_action='advance' when the current phase objective is met.",
            "  Suggested iteration allocation: RECON 2-3, ENUMERATION 3-5, VULN_SCAN 8-15, EXPLOITATION 5-10.",
            "  These are soft targets — spend MORE time on phases with promising attack surface.",
            "- Before setting phase_action='complete', list ALL techniques you have NOT yet tried",
            "  and justify skipping each one. If you cannot justify skipping a technique, run it first.",
            "  Minimum checklist before completion: nikto, full nuclei scan, security header analysis,",
            "  SSL/TLS check, robots.txt/sitemap.xml, and at least 5 injection payloads per discovered parameter.",
            "- EXPLOITATION gate: do not advance to REPORTING until every high/critical finding has",
            "  at least one concrete proof-of-concept attempt. Scanner output alone is not evidence —",
            "  confirm exploitability with a targeted request (curl, sqlmap, or a custom script).",
            "- When CLI tools are insufficient for a vector, write a python3 script instead.",
            "  Use the `write_file` action to drop the script cleanly into the sandbox (e.g. target_path='/tmp/exploit.py').",
            "  Then use a `launch` action to run it: `python3 /tmp/exploit.py`.",
            "  Use asyncio/aiohttp for concurrent payload sprays. Batch payloads into a single script",
            "  rather than issuing one command per attempt. Log status codes, response lengths,",
            "  and timing deltas to auto-triage anomalies.",
            "</constraints>",
            "",
            *__import__('kodiak.core.tools.registry', fromlist=['get_prompt_catalog']).get_prompt_catalog(),
            "",
        ]

        # WAF/CDN context
        if self.scan_state.waf_detected:
            sections.extend([
                "<waf_context>",
                "WAF/CDN detected. Adapt your approach — do not abandon testing.",
                "- Discover origin IPs: check DNS history, try direct IP access, check non-HTTP ports.",
                "- Target bypass subdomains: staging/dev/prelive servers often skip WAF.",
                "- Rate-limit HTTP tools: ffuf -t 5, katana -rl 10, nuclei -rl 20.",
                "- nmap is TCP-level — NOT affected by WAFs. Scan full port range.",
                "- Use curl for manual probing with encoding tricks, path normalization, custom headers.",
                "- Try HTTP/1.0, unusual methods (HEAD, OPTIONS), or chunk transfer encoding.",
                "- Do NOT waste commands on broad fuzzing against CDN-fronted domains (returns 503).",
                "</waf_context>",
                "",
            ])

        # Skills injection
        skills_text = self._load_skills()
        if skills_text:
            sections.append(skills_text)
            sections.append("")

        # Prior engagement knowledge
        if self._prior_knowledge:
            sections.append(self._prior_knowledge)
            sections.append("")

        # Recording guidance
        sections.extend([
            "<recording>",
            "Record ANY security-relevant observation as a finding, even without confirmed exploitation.",
            "An exposed admin panel IS a finding. Missing security headers ARE findings. Directory listings ARE findings.",
            "Use the `findings` array aggressively — it is better to over-report than to miss something.",
            "Use the `notes` array to record observations for future scans:",
            "  - recon_intel: infrastructure details (staging servers, CDNs, internal hostnames)",
            "  - behavioral: WAF behavior, rate limits, server quirks",
            "  - attack_hint: promising attack surface for deeper testing",
            "  - dead_end: paths that wasted time — skip these next time",
            "Severity anchors:",
            "  critical — RCE, auth bypass, full DB dump, direct code execution",
            "  high — Exposed credentials, LFI with sensitive file read, confirmed SQLi with data extraction",
            "  medium — Exposed admin panel (Umbraco, phpMyAdmin, cPanel), directory listing, .git exposed,",
            "           SSRF potential, exposed installer, misconfigured CORS",
            "  low — Missing security headers (CSP, X-Frame-Options, HSTS), weak SSL/TLS config,",
            "         cookie without Secure/HttpOnly flags, verbose error messages",
            "  info — Version disclosure, technology fingerprints, interesting endpoints, DNS records,",
            "          open ports with no obvious vulnerability, server banner information",
            "</recording>",
            "",
        ])

        # Scan state (context before task — Gemini 3 best practice)
        sections.extend([
            "<scan_state>",
            self.scan_state.to_prompt_context(),
            "</scan_state>",
            "",
        ])

        # Task at the very end (context-before-task pattern)
        sections.extend([
            "<task>",
            f"Current phase: {phase.value.upper()}. Objective: {phase_objectives.get(phase, '')}",
            "Based on the scan state above, output the most impactful actions/commands for this phase.",
            "Prioritise breadth in RECON/ENUMERATION. Prioritise depth in VULN_SCAN/EXPLOITATION.",
            "For each launch/cancel action, explain your rationale.",
            "Remember: you are relentless. Do not stop until you have exhausted every applicable technique.",
            "</task>",
        ])

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Skills injection
    # ------------------------------------------------------------------

    def _load_skills(self) -> str:
        """Load relevant skills based on detected technologies in scan state."""
        try:
            from kodiak.skills.skill_loader import skill_loader

            target_info: Dict[str, Any] = {
                "technologies": [],
                "services": [],
                "ports": [],
            }

            if self.scan_state:
                for ts in self.scan_state.targets.values():
                    target_info["technologies"].extend(ts.technologies)
                    target_info["ports"].extend(ts.ports)
                    target_info["services"].extend(list(ts.services.values()))

            suggested = skill_loader.suggest_skills_for_target(target_info)
            if suggested:
                # Limit to 3 skills to keep prompt concise (Gemini 3 best practice)
                return skill_loader.load_skills_for_agent(suggested, max_skills=3)
            return ""
        except Exception as exc:
            logger.debug(f"Skills loading skipped: {exc}")
            return ""

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_kodiak_response(self, content: str) -> Optional[KodiakResponse]:
        """Parse the LLM's JSON response into a KodiakResponse."""
        if not content:
            return None

        try:
            data = json.loads(content)
            return KodiakResponse.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(f"Failed to parse KodiakResponse: {exc}")
            # Try to extract JSON from markdown code block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    return KodiakResponse.model_validate(data)
                except Exception:
                    pass
            return None

    # ------------------------------------------------------------------
    # Discovery processing
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_hostname(host: str) -> str:
        """Normalize hostname by stripping www. prefix."""
        h = host.strip().lower()
        if h.startswith("www."):
            h = h[4:]
        return h

    def _apply_discoveries(self, resp: KodiakResponse) -> None:
        """Update ScanState from the LLM's structured discoveries."""
        disc = resp.discoveries
        if not disc:
            return

        for host in disc.hosts:
            if host and "." in host:
                norm = self._normalize_hostname(host)
                self.scan_state.ensure_target(norm)

        # ports is now List[HostPorts]
        for hp in disc.ports:
            norm = self._normalize_hostname(hp.host)
            ts = self.scan_state.ensure_target(norm)
            for port in hp.ports:
                if port not in ts.ports:
                    ts.ports.append(port)

        # technologies is now List[HostTechs]
        for ht in disc.technologies:
            norm = self._normalize_hostname(ht.host)
            ts = self.scan_state.ensure_target(norm)
            for tech in ht.technologies:
                if tech and tech not in ts.technologies and len(tech) < 60:
                    ts.technologies.append(tech)
            # Detect WAF/CDN presence
            if not self.scan_state.waf_detected:
                for tech in ht.technologies:
                    if re.search(
                        r'\bcloudflare\b|\bwaf\b|\bakamai\b|\bfastly\b|\bimperva\b',
                        tech, re.IGNORECASE
                    ):
                        self.scan_state.waf_detected = True
                        break

        for url in disc.urls:
            if url.startswith("http"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                if parsed.hostname:
                    norm = self._normalize_hostname(parsed.hostname)
                    ts = self.scan_state.ensure_target(norm)
                    if url not in ts.urls:
                        ts.urls.append(url)

    # ------------------------------------------------------------------
    # Command results formatting
    # ------------------------------------------------------------------

    def _format_command_results(self, results: List[CommandResult]) -> str:
        """Format command results as context for the next LLM iteration."""
        parts = ["<command_results>"]
        for cr in results:
            parts.append(cr.to_prompt_text())
            parts.append("")  # blank line separator
        parts.append("</command_results>")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Persistence — findings and notes
    # ------------------------------------------------------------------

    async def _persist_finding(
        self,
        finding,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> None:
        """Persist a structured finding from KodiakResponse to the database."""
        try:
            title = finding.title
            target = finding.target

            # Dedup check
            existing = await crud.finding.find_by_title_and_target(
                session, project_id, title, target,
            )
            if existing:
                logger.info(f"🔄 Finding already exists, skipping: {title}")
                return

            try:
                sev = FindingSeverity(finding.severity.value)
            except (ValueError, AttributeError):
                sev = FindingSeverity.INFO

            db_finding = Finding(
                project_id=project_id,
                scan_id=scan_id,
                target=target,
                title=title,
                description=finding.description[:4000],
                severity=sev,
                remediation=finding.remediation[:2000] if finding.remediation else None,
                raw_evidence=finding.evidence[:2000] if finding.evidence else None,
            )
            await crud.finding.create(session, db_finding)

            # Also record in scan state for prompt context
            self.scan_state.add_finding(
                title=title,
                severity=finding.severity.value,
                target=target,
                evidence=finding.evidence[:300] if finding.evidence else "",
            )

            logger.info(f"🎯 Finding saved [{finding.severity.value}]: {title}")

            if self.event_manager:
                try:
                    await self.event_manager.emit_finding_saved(
                        title=title,
                        severity=finding.severity.value,
                        target=target,
                        scan_id=str(scan_id),
                    )
                except Exception:
                    pass

        except Exception as exc:
            logger.warning(f"Failed to persist finding '{finding.title}': {exc}")

    async def _persist_note(
        self,
        note,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> None:
        """Persist a structured note from KodiakResponse to the database."""
        try:
            try:
                category = NoteCategory(note.category.value)
            except (ValueError, AttributeError):
                category = NoteCategory.GENERAL

            db_note = EngagementNote(
                project_id=project_id,
                scan_id=scan_id,
                category=category,
                target=note.target,
                content=note.content[:2000],
            )
            await crud.note.create(session, db_note)
            logger.info(f"📝 Note saved [{category.value}]: {note.content[:80]}")

            if self.event_manager:
                try:
                    await self.event_manager.emit_note_saved(
                        category=category.value,
                        target=note.target,
                        preview=note.content[:100],
                        scan_id=str(scan_id),
                    )
                except Exception:
                    pass

        except Exception as exc:
            logger.warning(f"Failed to persist note: {exc}")

    async def _persist_command_attempt(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        result: CommandResult,
    ) -> None:
        """Write a command execution record to the database."""
        try:
            if result.timed_out:
                status = "timeout"
            elif result.exit_code == 0:
                status = "success"
            else:
                status = "failed"

            # Extract tool name from command (first word)
            tool_name = result.command.split()[0] if result.command.strip() else "cmd"

            # Extract target from command if possible
            target = "unknown"
            url_match = re.search(r'https?://[^\s\'"]+', result.command)
            domain_match = re.search(r'-[duh]\s+([^\s]+)', result.command) if not url_match else None
            if url_match:
                target = url_match.group(0)
            elif domain_match:
                target = domain_match.group(1)

            await crud.attempt.create(
                session=session,
                attempt=Attempt(
                    project_id=project_id,
                    scan_id=scan_id,
                    tool=tool_name,
                    target=target,
                    status=status,
                    reason=result.stderr[:300] if result.stderr else None,
                    properties={
                        "agent_id": "manager",
                        "duration_seconds": result.duration_seconds,
                        "command": result.command[:500],
                        "rationale": result.rationale[:300],
                        "exit_code": result.exit_code,
                    },
                ),
            )
        except Exception as exc:
            logger.warning(f"Failed to persist attempt: {exc}")

    # ------------------------------------------------------------------
    # Prior knowledge loading
    # ------------------------------------------------------------------

    async def _load_prior_knowledge(
        self,
        session: Any,
        project_id: UUID,
    ) -> tuple[str, int, int]:
        """Load prior notes and findings for this project.

        Returns (xml_block, notes_count, findings_count).
        """
        try:
            notes = await crud.note.list_for_project(session, project_id, limit=30)
            findings = await crud.finding.list_for_project(session, project_id, limit=20)
        except Exception as exc:
            logger.warning(f"Failed to load prior knowledge: {exc}")
            return "", 0, 0

        if not notes and not findings:
            return "", 0, 0

        lines: List[str] = ["<prior_knowledge>"]

        if notes:
            lines.append(f'<prior_notes count="{len(notes)}">')
            for n in reversed(notes):  # oldest first
                date = n.created_at.strftime("%Y-%m-%d") if n.created_at else "?"
                lines.append(f"  [{date} {n.category.value}] ({n.target}) {n.content[:200]}")
            lines.append("</prior_notes>")

        if findings:
            lines.append(f'<prior_findings count="{len(findings)}">')
            for f in reversed(findings):  # oldest first
                sev = f.severity.value.upper() if f.severity else "INFO"
                target = f.target or "?"
                desc = (f.description or "")[:100]
                remediation = f"  Remediation: {f.remediation[:80]}" if f.remediation else ""
                lines.append(f"  [{sev}] {f.title} — {target}")
                if desc:
                    lines.append(f"    {desc}")
                if remediation:
                    lines.append(f"    {remediation}")
            lines.append("</prior_findings>")

        lines.append("</prior_knowledge>")

        block = "\n".join(lines)
        # Hard cap at ~12K chars (~3000 tokens)
        if len(block) > 12000:
            block = block[:11997] + "..."
        return block, len(notes), len(findings)

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _trim_history(self, history: List[Dict[str, Any]], max_turns: int = 80) -> List[Dict[str, Any]]:
        """Keep the first user message and the most recent turns."""
        if len(history) <= max_turns:
            return history
        # Always keep the initial scan_request
        head = history[:1]
        tail = history[-(max_turns - 1):]
        return head + tail

    # ------------------------------------------------------------------
    # Final findings persistence
    # ------------------------------------------------------------------

    async def _persist_final_findings(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> None:
        """Emit finding events and persist auto-extracted findings to DB."""
        if not self.scan_state:
            return
        for finding in self.scan_state.findings:
            try:
                await self.event_manager.emit_finding_discovered(
                    finding={
                        "title": finding.title,
                        "severity": finding.severity,
                        "target": finding.target,
                        "evidence": finding.evidence,
                        "tool": finding.tool,
                    },
                    agent_id="manager",
                    scan_id=str(scan_id),
                )
            except Exception as exc:
                logger.warning(f"Failed to emit finding event: {exc}")

            # Persist auto-extracted finding to DB with dedup check
            try:
                existing = await crud.finding.find_by_title_and_target(
                    session, project_id, finding.title, finding.target
                )
                if not existing:
                    try:
                        sev_enum = FindingSeverity(finding.severity.lower())
                    except ValueError:
                        sev_enum = FindingSeverity.INFO
                    db_finding = Finding(
                        project_id=project_id,
                        scan_id=scan_id,
                        target=finding.target,
                        title=finding.title,
                        description=finding.evidence[:4000] if finding.evidence else "",
                        severity=sev_enum,
                        tool=finding.tool or None,
                        raw_evidence=finding.evidence[:2000] if finding.evidence else None,
                    )
                    await crud.finding.create(session, db_finding)
            except Exception as exc:
                logger.warning(f"Failed to persist auto-extracted finding '{finding.title}': {exc}")

    # ------------------------------------------------------------------
    # Legacy helpers (kept for test compatibility)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_args(raw: Any) -> Dict[str, Any]:
        """Parse tool arguments from string or dict."""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def _check_phase_advance(self, assistant_text: str, scan_id: str = "") -> bool:
        """Check if the Manager explicitly requested a phase advance.
        
        Kept for backward compatibility with tests, but phase advancement
        is now driven by the structured phase_action field.
        """
        if not assistant_text:
            return False
        if "ADVANCE_PHASE" in assistant_text.upper():
            old_phase = self.scan_state.phase.value
            advanced = self.scan_state.advance_phase()
            if advanced:
                logger.info(f"📍 Phase advanced to: {self.scan_state.phase.value}")
            return advanced
        return False
