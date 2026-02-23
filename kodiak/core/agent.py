from typing import Any, Dict, List, Optional
import json
import asyncio
import time
import hashlib
import re
from contextlib import AsyncExitStack
from uuid import uuid4, UUID
from dataclasses import dataclass
from loguru import logger

import litellm
from litellm import acompletion

from kodiak.core.config import settings
from kodiak.core.blackboard import BlackboardService
from kodiak.core.memory import InsightMemoryService
from kodiak.core.memory_central import CentralMemoryService
from kodiak.core.failure_policy import apply_timeout_backoff
from kodiak.core.tools.base import ToolResult
from kodiak.services import llm


@dataclass
class AgentResult:
    """Result of an agent run"""
    status: str  # "completed", "max_iterations", "failed", "cancelled"
    summary: str
    findings_count: int
    iterations: int


class FallbackResponse:
    """Fallback response for LLM failures"""
    def __init__(self, error_msg):
        self.content = f"Error in agent thinking: {error_msg}. Continuing with mission."
        self.tool_calls = None


class KodiakAgent:
    """
    The Brain. 
    Autonomous agent that can think, act, and execute security scans.
    """
    def __init__(
        self, 
        agent_id: str, 
        tool_inventory, 
        event_manager, 
        model_name: str = None, 
        session: Any = None, 
        role: str = "generalist", 
        project_id: Any = None, 
        skills: Optional[List[str]] = None,
        global_tool_semaphore: Optional[asyncio.Semaphore] = None,
        tool_semaphores: Optional[Dict[str, asyncio.Semaphore]] = None,
        tool_scheduler: Any = None,
        allowed_tools: Optional[List[str]] = None,
    ):
        self.agent_id = agent_id
        self.model_name = model_name or settings.llm_model
        self.session = session
        self.role = role
        self.project_id = project_id
        self.tool_inventory = tool_inventory
        self.event_manager = event_manager
        self.loaded_skills: List[str] = skills or []
        self.skills_knowledge: str = ""
        self._hive_mind = None
        self._current_iteration = 0
        self.scan_id: Optional[UUID] = None
        self._global_tool_semaphore = global_tool_semaphore
        self._tool_semaphores = tool_semaphores or {}
        self._tool_scheduler = tool_scheduler
        self._limited_heavy_tools = {"nmap", "sqlmap", "nuclei", "ffuf", "katana"}

        # Lightweight in-run memory for tool deduplication/backoff.
        self._tool_attempts: List[Dict[str, Any]] = []
        self._attempts_by_fingerprint: Dict[str, List[Dict[str, Any]]] = {}
        self._persisted_insights: List[Dict[str, Any]] = []
        self._persisted_do_not_repeat: Dict[str, str] = {}
        self._insight_memory_service = InsightMemoryService(self.model_name)
        self._central_memory_service = CentralMemoryService()
        self._blackboard_service = BlackboardService()
        self._central_memory_context = ""
        self._blackboard_context = ""
        self._scan_target: str = ""
        self._strict_dedupe_tools = {
            "nmap",
            "nuclei",
            "sqlmap",
            "ffuf",
            "katana",
            "httpx",
            "whatweb",
            "searchsploit",
        }
        self._page_fetch_commands = ("curl ", "wget ", "http ")
        
        # Use actual tool names from inventory, optionally gated per-scan.
        registered_tools = [tool_name for tool_name in self.tool_inventory.list_tools().keys()]
        if allowed_tools:
            allowed_set = set(allowed_tools)
            self.available_tools = [name for name in registered_tools if name in allowed_set]
        else:
            self.available_tools = registered_tools
        
        # Load skills if provided
        if self.loaded_skills:
            self._load_agent_skills()
    
    async def register_with_hive_mind(self):
        """Register this agent with the Hive Mind for state synchronization"""
        from kodiak.core.hive_mind import hive_mind
        self._hive_mind = hive_mind
        
        if self.project_id:
            await hive_mind.register_agent(
                agent_id=self.agent_id,
                project_id=str(self.project_id),
                role=self.role
            )
    
    async def unregister_from_hive_mind(self):
        """Unregister this agent from the Hive Mind"""
        if self._hive_mind:
            await self._hive_mind.unregister_agent(self.agent_id)
    
    async def share_discovery(self, discovery: Dict[str, Any]) -> Dict[str, Any]:
        """Share a discovery with other agents via the Hive Mind"""
        if not self._hive_mind or not self.project_id:
            return discovery
        
        return await self._hive_mind.share_discovery(
            agent_id=self.agent_id,
            project_id=str(self.project_id),
            discovery=discovery,
            scan_id=str(self.project_id)
        )
    
    async def get_shared_discoveries(self, since=None) -> List[Dict[str, Any]]:
        """Get discoveries shared by other agents"""
        if not self._hive_mind or not self.project_id:
            return []
        
        return await self._hive_mind.get_shared_discoveries(
            project_id=str(self.project_id),
            since=since
        )
    
    async def get_peer_agents(self) -> Dict[str, Dict[str, Any]]:
        """Get information about other active agents in the same project"""
        if not self._hive_mind or not self.project_id:
            return {}
        
        return await self._hive_mind.get_active_agents(str(self.project_id))

    def _load_agent_skills(self):
        """Load specialized skills for this agent"""
        try:
            from kodiak.skills import skill_loader
            self.skills_knowledge = skill_loader.load_skills_for_agent(self.loaded_skills)
        except Exception as e:
            logger.warning(f"Failed to load skills: {e}")
            self.skills_knowledge = ""

    def add_skills(self, skill_names: List[str]):
        """Add additional skills to the agent"""
        self.loaded_skills.extend(skill_names)
        self.loaded_skills = list(set(self.loaded_skills))  # Remove duplicates
        self._load_agent_skills()

    async def run(
        self, 
        goal: str, 
        target: str, 
        session: Any, 
        project_id: UUID, 
        scan_id: UUID, 
        max_iterations: int = 100
    ) -> AgentResult:
        """
        Run the full think-act loop.
        
        Returns when:
        - Agent calls complete_scan tool
        - max_iterations reached
        - Error occurs
        """
        logger.info(f"🚀 Agent {self.agent_id} starting run for goal: {goal}")
        self.scan_id = scan_id
        self._scan_target = target
        await self._load_persisted_insight_memory(session, scan_id)
        
        history = [
            {
                "role": "user", 
                "content": (
                    "<scan_request>\n"
                    f"<goal>{goal}</goal>\n"
                    f"<target>{target}</target>\n"
                    "<requirements>\n"
                    "- Use tools systematically.\n"
                    "- Reuse prior evidence before retrying tools.\n"
                    "- When objective is met, call complete_scan with concise findings.\n"
                    "</requirements>\n"
                    "</scan_request>"
                )
            }
        ]
        
        iterations = 0
        findings_count = 0
        
        while iterations < max_iterations:
            iterations += 1
            self._current_iteration = iterations
            logger.debug(f"🔄 Iteration {iterations}/{max_iterations}")
            
            # --- Max Iteration Warning System ---
            if max_iterations > 10:
                if iterations == int(max_iterations * 0.85):
                    remaining = max_iterations - iterations
                    history.append({
                        "role": "user",
                        "content": (
                            "<iteration_warning>\n"
                            f"Current: {iterations}/{max_iterations}.\n"
                            f"Remaining: {remaining} iterations.\n"
                            "Prioritize completion and call complete_scan as soon as the objective is satisfied.\n"
                            "</iteration_warning>"
                        )
                    })
                elif iterations == max_iterations - 3:
                    history.append({
                        "role": "user",
                        "content": (
                            "<final_iteration_warning>\n"
                            "Only 3 iterations remain.\n"
                            "Finish immediately: produce final evidence and call complete_scan.\n"
                            "</final_iteration_warning>"
                        )
                    })
            # ------------------------------------
            
            # 1. Think
            response = await self.think(history)
            
            # Broadcast the agent's thoughts so they appear in `--verbose` logs
            if response.content and self.event_manager:
                await self.event_manager.emit_agent_thought(
                    agent_id=self.agent_id,
                    thought=response.content,
                    scan_id=str(self.project_id) if self.project_id else None
                )
            
            
            # 2. Act
            if response.tool_calls:
                # Add assistant message with tool calls to history
                # Sanitize tool call IDs for Gemini 3
                sanitized_tool_calls = []
                for tc in response.tool_calls:
                    tc_dict = tc.dict() if hasattr(tc, 'dict') else tc
                    if 'id' in tc_dict and '__thought__' in tc_dict['id']:
                        tc_dict['id'] = tc_dict['id'].split('__thought__')[0]
                    sanitized_tool_calls.append(tc_dict)

                history.append({
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": sanitized_tool_calls
                })
                
                for tool_call in response.tool_calls:
                    tool_name = tool_call.function.name
                    # sanitize ID here too for the response
                    original_id = tool_call.id
                    clean_id = original_id.split('__thought__')[0] if '__thought__' in original_id else original_id
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                        
                    # Extract the synthetic 'thought' parameter Gemini uses to explain actions
                    thought = args.pop("thought", None)
                    if thought and not response.content and self.event_manager:
                        await self.event_manager.emit_agent_thought(
                            agent_id=self.agent_id,
                            thought=thought,
                            scan_id=str(self.project_id) if self.project_id else None
                        )
                    
                    # Execute action
                    result = await self.act(
                        tool_name=tool_name,
                        args=args,
                        thought=thought,
                        session=session,
                        project_id=project_id,
                        scan_id=scan_id
                    )
                    
                    # Add tool result to history
                    history.append({
                        "role": "tool",
                        "tool_call_id": clean_id,
                        "content": self._build_tool_history_content(result)
                    })
                    
                    # Check for structured completion
                    if tool_name == "complete_scan":
                        summary = result.get("data", {}).get("summary", "Scan complete")
                        findings = result.get("data", {}).get("findings_count", 0)
                        return AgentResult(
                            status="completed",
                            summary=summary,
                            findings_count=findings,
                            iterations=iterations
                        )
            else:
                # No tool calls, just a text response
                history.append({"role": "assistant", "content": response.content})
                
                # Nudge the agent to continue if it hasn't finished
                history.append({
                    "role": "user",
                    "content": (
                        "<next_step>\n"
                        "Continue scan.\n"
                        "If objective is met, call complete_scan now.\n"
                        "</next_step>"
                    )
                })
                
        return AgentResult(
            status="max_iterations",
            summary=f"Reached maximum of {max_iterations} iterations",
            findings_count=findings_count,
            iterations=iterations
        )

    async def think(self, history: List[Dict[str, Any]], custom_prompt: str = None) -> Any:
        """
        Generates a reasoning step and potential actions using LiteLLM.
        """
        try:
            # Load context from DB
            context_str = await self._load_context(self.session, self.project_id)
            if settings.blackboard_enabled and self.session and self.scan_id:
                self._blackboard_context = await self._blackboard_service.build_prompt_context(
                    session=self.session,
                    scan_id=self.scan_id,
                    role=self.role,
                    target=self._scan_target,
                    limit=settings.blackboard_context_limit,
                )
                if self._blackboard_context:
                    context_str = (
                        f"{context_str}\n{self._blackboard_context}"
                        if context_str
                        else self._blackboard_context
                    )
            if settings.memory_central_enabled and self.session and self.scan_id:
                self._central_memory_context = await self._central_memory_service.build_prompt_context(
                    session=self.session,
                    scan_id=self.scan_id,
                    limit=settings.memory_recent_in_prompt,
                    agent_id=self.agent_id,
                )
            runtime_memory = self._build_runtime_memory_context()
            if runtime_memory:
                context_str = f"{context_str}\n{runtime_memory}" if context_str else runtime_memory
            system_prompt = self._build_system_prompt(custom_prompt, context_str)
            
            # Prepare tools
            tools = self._prepare_tools()
            
            # Prepare messages
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add summarized heart of history
            condensed_history = await self._summarize_history(history)
            
            # Gemini Turn Ordering Fix:
            # The conversation (after system prompt) MUST start with a user message.
            # If truncation left us starting with an assistant message, prepend a dummy user message.
            if condensed_history and condensed_history[0].get("role") == "assistant":
                condensed_history.insert(0, {
                    "role": "user",
                    "content": "..."  # Minimal continuation prompt to satisfy alternating roles
                })
                
            messages.extend(condensed_history)
            
            # Enforce thinking before tool calls
            # Models like Gemini 3 Flash often skip the 'content' block 
            # if we don't explicitly prompt them at the end of the chain.
            if len(messages) > 0 and messages[-1].get("role") != "user":
                messages.append({
                    "role": "user",
                    "content": (
                        "Based on the context above, provide a concise CONTEXT/THEORY/PLAN explanation before any tool call. "
                        "Then execute the best next action."
                    )
                })
            elif len(messages) > 0 and messages[-1].get("role") == "user":
                # Inject it into the existing user message if it's not empty
                orig_content = messages[-1].get("content", "")
                if orig_content and "context/theory/plan" not in orig_content.lower():
                    messages[-1]["content"] = (
                        orig_content
                        + "\n\n(Based on the context above, include a concise CONTEXT/THEORY/PLAN before any tool call.)"
                    )
                    
            # Get LLM configuration
            provider = llm.infer_provider_from_model(self.model_name)
            api_key = llm.get_api_key_for_provider(provider)
            
            # Prepare completion parameters
            completion_params = {
                "model": self.model_name,
                "messages": messages,
                "temperature": settings.llm_temperature,
                "max_tokens": settings.llm_max_tokens,
                "tools": tools if tools else None,
                "tool_choice": "auto" if tools else None,
            }
            
            if api_key:
                completion_params["api_key"] = api_key
            
            # Emit thinking event
            if self.event_manager:
                await self.event_manager.emit_agent_thinking(
                    agent_id=self.agent_id,
                    message="Planning next action",
                    scan_id=str(self.project_id) if self.project_id else None
                )
            
            # Call LLM
            response = await acompletion(**completion_params)
            return response.choices[0].message
            
        except Exception as e:
            logger.error(f"Agent thinking failed: {e}")
            return FallbackResponse(str(e))

    def _build_system_prompt(self, custom_prompt: str = None, context_str: str = "") -> str:
        """Build comprehensive system prompt"""
        if custom_prompt:
            base_prompt = custom_prompt
        elif self.role == "scout":
            base_prompt = "You are a SCOUT agent specialized in reconnaissance."
        elif self.role == "attacker":
            base_prompt = "You are an ATTACKER agent specialized in exploitation."
        else:
            base_prompt = "You are KODIAK, an autonomous penetration testing agent."

        sections: List[str] = [
            "<system_instruction>",
            "<role>",
            base_prompt,
            "</role>",
            "<objective>",
            "Find high-impact security issues with reproducible evidence.",
            "</objective>",
            "<execution_environment>",
            "All tools execute inside a Kali Docker container.",
            "Use only registered tools and their schemas.",
            "</execution_environment>",
            "<hard_constraints>",
            "- Do not repeat identical tool calls unless parameters or strategy changed.",
            "- For page analysis, fetch once and extract headers/forms/hidden fields/tokens/cookies together.",
            "- If a tool times out, retry once with lower intensity; do not repeat unchanged calls.",
            "- If blocked/rate-limited, record as environment signal and pivot strategy.",
            "- Read BLACKBOARD peer outcomes before retrying; if you retry, state what changed.",
            "- Keep responses concise by default.",
            "- Call complete_scan only after the objective is fully covered.",
            "</hard_constraints>",
            "<planning_format>",
            "Before every tool call, set tool argument `thought` using this exact structure:",
            "CONTEXT: relevant evidence from prior output.",
            "THEORY: concrete hypothesis to validate.",
            "PLAN: why this tool+args is the best next action.",
            "Keep `thought` concise (max 6 lines).",
            "</planning_format>",
        ]

        if self.skills_knowledge:
            sections.extend([
                "<skills_knowledge>",
                self.skills_knowledge,
                "</skills_knowledge>",
            ])

        if context_str:
            sections.extend([
                "<shared_context>",
                context_str,
                "</shared_context>",
            ])

        sections.extend([
            "<final_instruction>",
            "Based on the context above, choose the best next action and avoid duplicate execution.",
            "</final_instruction>",
            "</system_instruction>",
        ])
        return "\n".join(sections)

    def _prepare_tools(self, allowed_tools: List[str] = None) -> List[Dict[str, Any]]:
        """Prepare tool definitions for LLM"""
        available_tools = []
        all_tools = self.tool_inventory.list_tools()
        
        filtered_names = allowed_tools if allowed_tools else self.available_tools
        
        for tool_name in filtered_names:
            tool_instance = self.tool_inventory.get(tool_name)
            if tool_instance:
                available_tools.append(tool_instance.to_openai_schema())
        
        return available_tools

    async def _load_context(self, session: Any, project_id: Any) -> str:
        """Queries the DB for facts relevant to this project"""
        if not session or not project_id:
            return ""
            
        context_str = "CURRENT PROJECT CONTEXT:\n"
        
        try:
            from kodiak.database.models import Node, Finding
            from sqlmodel import select
            
            # Fetch nodes
            stmt_nodes = select(Node).where(Node.project_id == project_id).limit(10)
            result = await session.execute(stmt_nodes)
            nodes = result.scalars().all()
            
            if nodes:
                context_str += "DISCOVERED ASSETS:\n"
                for node in nodes:
                    context_str += f"  - {node.type}: {node.name}\n"
            
            # Add more context if needed...
                
        except Exception as e:
            logger.error(f"Error loading context: {e}")
        
        return context_str

    async def _summarize_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep history within reasonable limits, respecting Gemini's strict turn ordering.

        Rules enforced:
        1. Never start the slice on a 'tool' message (orphaned tool response).
        2. Never end the slice on an assistant message that has tool_calls but
           no following tool response (Gemini: function call must be followed by
           a function response turn).
        3. Never have two consecutive non-assistant messages without an assistant
           message in between.
        """
        max_messages = 28  # keep last N messages
        if len(history) <= max_messages:
            return self._sanitize_for_gemini(history)

        # Walk forward from the naive cut until we land on a non-tool message
        cut = len(history) - max_messages
        while cut < len(history) and history[cut].get("role") == "tool":
            cut += 1

        return self._sanitize_for_gemini(history[cut:])

    async def _load_persisted_insight_memory(self, session: Any, scan_id: UUID) -> None:
        if not session or not scan_id:
            return
        await self._ensure_insight_table_ready(session)
        try:
            from kodiak.database.crud import insight_memory

            records = await insight_memory.list_by_scan(
                session=session,
                scan_id=scan_id,
                limit=settings.memory_max_entries,
            )
            self._persisted_insights = []
            self._persisted_do_not_repeat = {}
            for record in reversed(records):
                entry = {
                    "tool": record.tool,
                    "target": record.target,
                    "fingerprint": record.fingerprint,
                    "status": record.status,
                    "insight": record.insight or {},
                }
                self._persisted_insights.append(entry)
                do_not_repeat = str((record.insight or {}).get("do_not_repeat") or "").strip()
                if do_not_repeat:
                    self._persisted_do_not_repeat[record.fingerprint] = do_not_repeat
        except Exception as e:
            error_text = str(e).lower()
            if "no such table" in error_text and "insightmemory" in error_text:
                try:
                    from kodiak.database.engine import init_db
                    from kodiak.database.crud import insight_memory

                    await init_db()
                    records = await insight_memory.list_by_scan(
                        session=session,
                        scan_id=scan_id,
                        limit=settings.memory_max_entries,
                    )
                    self._persisted_insights = []
                    self._persisted_do_not_repeat = {}
                    for record in reversed(records):
                        entry = {
                            "tool": record.tool,
                            "target": record.target,
                            "fingerprint": record.fingerprint,
                            "status": record.status,
                            "insight": record.insight or {},
                        }
                        self._persisted_insights.append(entry)
                        do_not_repeat = str((record.insight or {}).get("do_not_repeat") or "").strip()
                        if do_not_repeat:
                            self._persisted_do_not_repeat[record.fingerprint] = do_not_repeat
                except Exception as retry_error:
                    logger.warning(
                        f"Could not load persisted insight memory for scan {scan_id} after init_db retry: {retry_error}"
                    )
            else:
                logger.warning(f"Could not load persisted insight memory for scan {scan_id}: {e}")

    async def _ensure_insight_table_ready(self, session: Any) -> None:
        """Avoid noisy first-query failures on upgraded databases missing insightmemory."""
        if not settings.memory_enabled or not session:
            return
        try:
            from sqlalchemy import text

            table_exists = False
            if settings.is_sqlite:
                check = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='insightmemory'")
                )
                table_exists = check.scalar_one_or_none() is not None
            else:
                check = await session.execute(text("SELECT to_regclass('public.insightmemory')"))
                table_exists = check.scalar_one_or_none() is not None

            if not table_exists:
                from kodiak.database.engine import init_db

                await init_db()
        except Exception as e:
            logger.warning(f"Could not verify/prepare insightmemory table: {e}")

    def _sanitize_for_gemini(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove any assistant+tool_calls messages that have no following tool response.
        
        Gemini requires: assistant(tool_calls) → tool(response) pairs to be complete.
        An assistant message with tool_calls that has no following tool message
        causes INVALID_ARGUMENT errors.
        """
        result = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role")
            tool_calls = msg.get("tool_calls")

            if role == "assistant" and tool_calls:
                # Check that the next message(s) are tool responses for each call
                j = i + 1
                expected_ids = {tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                                for tc in tool_calls}
                found_ids = set()
                while j < len(messages) and messages[j].get("role") == "tool":
                    found_ids.add(messages[j].get("tool_call_id"))
                    j += 1

                if expected_ids and not found_ids:
                    # This assistant tool_call has no following tool response — skip it
                    i += 1
                    continue

            result.append(msg)
            i += 1

        return result

    def _build_runtime_memory_context(self) -> str:
        """Build compact run-state memory to reduce repeated tool calls."""
        if not self._tool_attempts and not self._persisted_insights and not self._central_memory_context:
            return ""

        lines = ["RUNTIME MEMORY (reuse these results and avoid duplicates):"]

        if self._central_memory_context:
            lines.append(self._central_memory_context)

        recent_persisted = self._persisted_insights[-settings.memory_recent_in_prompt:]
        if recent_persisted:
            lines.append("RECENT INSIGHTS:")
            for entry in recent_persisted:
                insight = entry.get("insight", {})
                what = (insight.get("what_was_tested") or f"{entry.get('tool')} {entry.get('target')}").strip()
                observations = insight.get("key_observations") or []
                next_actions = insight.get("next_best_actions") or []
                do_not_repeat = str(insight.get("do_not_repeat") or "").strip()
                obs_text = observations[0] if observations else ""
                next_text = next_actions[0] if next_actions else ""
                line = f"- [{entry.get('status', 'unknown').upper()}] {what}"
                if obs_text:
                    line += f" | obs: {obs_text}"
                if next_text:
                    line += f" | next: {next_text}"
                if do_not_repeat:
                    line += f" | avoid: {do_not_repeat}"
                lines.append(line)

        for attempt in self._tool_attempts[-settings.memory_recent_in_prompt:]:
            status = "SUCCESS"
            if not attempt.get("success"):
                status = "TIMEOUT" if attempt.get("timed_out") else "FAILED"
            lines.append(
                f"- Iter {attempt.get('iteration', '?')}: {attempt.get('tool')} [{status}] "
                f"{attempt.get('summary', '')}"
            )

        return "\n".join(lines)

    def _normalize_command(self, command: str) -> str:
        return " ".join((command or "").split()).strip()

    def _normalize_args_for_fingerprint(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {k: v for k, v in args.items() if k not in {"agent_id", "scan_id", "thought"}}

        if tool_name == "terminal_execute":
            # Session IDs vary, but command identity is what matters for repeated fetches.
            normalized.pop("session_id", None)
            normalized.pop("capture_output", None)
            normalized["command"] = self._normalize_command(str(args.get("command", "")))

        return normalized

    def _build_tool_summary(self, tool_name: str, args: Dict[str, Any]) -> str:
        if tool_name == "terminal_execute":
            command = self._normalize_command(str(args.get("command", "")))
            if len(command) > 120:
                command = command[:117] + "..."
            return command

        for key in ("target", "url", "domain", "query", "exploit_id"):
            if args.get(key):
                value = str(args.get(key))
                if len(value) > 120:
                    value = value[:117] + "..."
                return f"{key}={value}"

        return "args=" + json.dumps(args, sort_keys=True, default=str)[:120]

    def _fingerprint_tool_call(self, tool_name: str, args: Dict[str, Any]) -> str:
        normalized_args = self._normalize_args_for_fingerprint(tool_name, args)
        payload = json.dumps(normalized_args, sort_keys=True, default=str, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return f"{tool_name}:{digest}"

    def _extract_tool_target(self, tool_name: str, args: Dict[str, Any]) -> str:
        if tool_name == "sqlmap":
            return str(args.get("url", "")).strip().lower()
        if tool_name == "ffuf":
            return str(args.get("url", "")).strip().lower()
        if tool_name == "nuclei":
            return str(args.get("target", "")).strip().lower()
        if tool_name == "terminal_execute":
            return self._normalize_command(str(args.get("command", ""))).lower()

        return str(args.get("target") or args.get("url") or args.get("domain") or "").strip().lower()

    def _count_prior_timeouts_in_run(self, tool_name: str, target_key: str) -> int:
        if not target_key:
            return 0
        count = 0
        for attempt in reversed(self._tool_attempts):
            if attempt.get("tool") != tool_name:
                continue
            if attempt.get("target_key") != target_key:
                continue
            if attempt.get("timed_out"):
                count += 1
        return count

    def _maybe_backoff_tool_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        timeout_count: int,
    ) -> tuple[Dict[str, Any], Optional[str], Optional[str]]:
        """
        Apply policy-based backoff and stop conditions after timeout(s).
        """
        adjusted, note, stop_reason = apply_timeout_backoff(
            tool_name=tool_name,
            args=args,
            timeout_count=timeout_count,
        )
        return adjusted, note, stop_reason

    def _should_skip_tool_call(self, tool_name: str, args: Dict[str, Any], fingerprint: str) -> Optional[str]:
        prior_attempts = self._attempts_by_fingerprint.get(fingerprint, [])
        if not prior_attempts:
            return None

        last = prior_attempts[-1]
        if last.get("success"):
            if tool_name in self._strict_dedupe_tools:
                return (
                    f"Skipping duplicate {tool_name} call with identical parameters. "
                    "Reuse prior output and pivot to a different scope/tool/parameter set."
                )
            if tool_name == "terminal_execute":
                command = self._normalize_command(str(args.get("command", ""))).lower()
                if command.startswith(self._page_fetch_commands):
                    return (
                        "Skipping duplicate page fetch command. Reuse the previous HTTP response and extract all needed "
                        "details (headers/forms/tokens/cookies) from that cached output."
                    )

        if last.get("timed_out"):
            return (
                f"Skipping identical retry for {tool_name}: previous attempt timed out. "
                "Reduce intensity before retrying."
            )

        return None

    def _result_to_dict(self, result: ToolResult | Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(result, ToolResult):
            return result.model_dump() if hasattr(result, "model_dump") else result.dict()
        return result

    def _is_timeout_result(self, result: ToolResult | Dict[str, Any]) -> bool:
        if isinstance(result, ToolResult):
            text = f"{result.error or ''} {result.output or ''}".lower()
        else:
            text = f"{result.get('error', '')} {result.get('output', '')}".lower()
        return "timeout" in text or "timed out" in text

    def _record_tool_attempt(
        self,
        tool_name: str,
        args: Dict[str, Any],
        fingerprint: str,
        result: ToolResult | Dict[str, Any],
    ) -> None:
        result_dict = self._result_to_dict(result)
        target_key = self._extract_tool_target(tool_name, args)

        attempt_record = {
            "iteration": self._current_iteration,
            "tool": tool_name,
            "fingerprint": fingerprint,
            "target_key": target_key,
            "args": self._normalize_args_for_fingerprint(tool_name, args),
            "summary": self._build_tool_summary(tool_name, args),
            "success": bool(result_dict.get("success", False)),
            "timed_out": self._is_timeout_result(result),
            "error": result_dict.get("error"),
            "output_preview": str(result_dict.get("output", ""))[:300],
            "timestamp": time.time(),
        }

        self._tool_attempts.append(attempt_record)
        self._attempts_by_fingerprint.setdefault(fingerprint, []).append(attempt_record)

    async def _persist_insight_memory(
        self,
        session: Any,
        project_id: Any,
        scan_id: Any,
        tool_name: str,
        target: str,
        fingerprint: str,
        args: Dict[str, Any],
        result_dict: Dict[str, Any],
    ) -> None:
        if not session or not project_id or not scan_id:
            return
        try:
            insight_entry = await self._insight_memory_service.generate_and_store(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                tool_name=tool_name,
                target=target,
                fingerprint=fingerprint,
                args=args,
                result=result_dict,
            )
            if not insight_entry:
                return

            self._persisted_insights.append(insight_entry)
            do_not_repeat = str((insight_entry.get("insight", {}) or {}).get("do_not_repeat") or "").strip()
            if do_not_repeat:
                self._persisted_do_not_repeat[fingerprint] = do_not_repeat

            if len(self._persisted_insights) > settings.memory_max_entries:
                self._persisted_insights = self._persisted_insights[-settings.memory_max_entries:]
        except Exception as e:
            logger.warning(f"Failed to persist insight memory for {tool_name}: {e}")

    async def _persist_central_memory(
        self,
        session: Any,
        project_id: Any,
        scan_id: Any,
        tool_name: str,
        target: str,
        fingerprint: str,
        args: Dict[str, Any],
        result_dict: Dict[str, Any],
        status_override: Optional[str] = None,
        reason_override: Optional[str] = None,
        extra_properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not settings.memory_central_enabled:
            return
        try:
            await self._central_memory_service.record_attempt(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                agent_id=self.agent_id,
                tool_name=tool_name,
                target=target or "unknown",
                fingerprint=fingerprint,
                args=args,
                result=result_dict,
                status_override=status_override,
                reason_override=reason_override,
                extra_properties=extra_properties,
            )
        except Exception as e:
            logger.warning(f"Failed to persist central memory for {tool_name}: {e}")

    async def _persist_central_state(
        self,
        session: Any,
        project_id: Any,
        scan_id: Any,
        tool_name: str,
        target: str,
        fingerprint: str,
        args: Dict[str, Any],
        status: str,
        reason: Optional[str] = None,
        extra_properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not settings.memory_central_enabled:
            return
        try:
            await self._central_memory_service.record_state(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                agent_id=self.agent_id,
                tool_name=tool_name,
                target=target or "unknown",
                fingerprint=fingerprint,
                args=args,
                status=status,
                reason=reason,
                properties=extra_properties,
            )
        except Exception as e:
            logger.warning(f"Failed to persist central memory state for {tool_name}: {e}")

    async def _persist_blackboard_tool_result(
        self,
        session: Any,
        project_id: Any,
        scan_id: Any,
        tool_name: str,
        target: str,
        fingerprint: str,
        args: Dict[str, Any],
        result_dict: Dict[str, Any],
        status: str,
        outcome: str,
        next_step: str,
        strategy: str,
    ) -> None:
        if not settings.blackboard_enabled or not session or not project_id or not scan_id:
            return
        try:
            await self._blackboard_service.publish_tool_result(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                agent_id=self.agent_id,
                tool_name=tool_name,
                target=target or "unknown",
                args=args,
                result=result_dict,
                fingerprint=fingerprint,
                execution_context={
                    "iteration": self._current_iteration,
                    "status": status,
                    "outcome": outcome,
                    "next_step": next_step,
                    "strategy": strategy,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to persist blackboard memory for {tool_name}: {e}")

    def _trim_text(self, text: Optional[str], limit: int = 220) -> str:
        cleaned = " ".join((text or "").split()).strip()
        if len(cleaned) > limit:
            return cleaned[: limit - 3] + "..."
        return cleaned

    def _classify_execution_outcome(
        self,
        _tool_name: str,
        result_dict: Dict[str, Any],
        coalesced: bool = False,
    ) -> tuple[str, str, str]:
        status = "success" if result_dict.get("success") else "failure"
        error_text = str(result_dict.get("error") or "")
        output_text = str(result_dict.get("output") or "")
        combined = f"{error_text} {output_text}".lower()

        if coalesced:
            return (
                "coalesced",
                "coalesced_peer_execution",
                "Reuse the shared peer output. Do not infer vulnerability or safety from coalescing alone.",
            )
        if "timeout" in combined or "timed out" in combined:
            return (
                "timeout",
                "timeout",
                "Retry once with lower intensity (fewer threads/rate/level) before pivoting.",
            )
        if error_text.startswith("Skipping "):
            return (
                "skipped",
                "skipped_duplicate_or_policy",
                "Do not retry unchanged parameters. Change scope, target, or tool strategy.",
            )
        if not result_dict.get("success"):
            if "not found" in combined or "exit code 127" in combined:
                return (
                    "failure",
                    "tool_missing",
                    "Treat as environment/tooling issue. Switch tool or install missing binary.",
                )
            if any(token in combined for token in ("403", "429", "forbidden", "cloudflare", "blocked", "waf")):
                return (
                    "failure",
                    "target_blocked_or_rate_limited",
                    "Reduce request intensity and pivot validation method; do not assume non-vulnerable.",
                )
            return (
                "failure",
                "execution_error",
                "Inspect stderr/response and adjust parameters before retrying.",
            )

        if any(token in combined for token in ("no results", "no matches", "0 results", "not vulnerable")):
            return (
                status,
                "executed_no_signal",
                "Use this as negative evidence only for this exact probe configuration.",
            )

        return (
            status,
            "executed_success",
            "Use this output as baseline context before planning follow-up probes.",
        )



    async def act(
        self, 
        tool_name: str, 
        args: Dict[str, Any], 
        thought: Optional[str] = None,
        session: Any = None, 
        project_id: Any = None, 
        scan_id: Any = None
    ) -> Dict[str, Any]:
        """
        Execute a tool action.
        """
        tool = self.tool_inventory.get(tool_name)
        if not tool:
            return {"error": f"Tool {tool_name} not found", "success": False}
        
        target = args.get('target', args.get('url', 'unknown'))
        target_key = self._extract_tool_target(tool_name, args)
        strategy = self._trim_text(thought, limit=280)
        
        try:
            # Prevent duplicate loops and apply failure policy after prior timeouts.
            in_run_timeouts = self._count_prior_timeouts_in_run(tool_name, target_key)
            central_timeouts = await self._central_memory_service.timeout_count_for_target(
                session=session,
                scan_id=scan_id,
                tool_name=tool_name,
                target_key=target_key,
            )
            timeout_count = in_run_timeouts + central_timeouts
            adjusted_args, backoff_note, stop_reason = self._maybe_backoff_tool_args(
                tool_name,
                args,
                timeout_count=timeout_count,
            )
            fingerprint = self._fingerprint_tool_call(tool_name, adjusted_args)
            lifecycle_properties = {"iteration": self._current_iteration}
            if strategy:
                lifecycle_properties["strategy"] = strategy

            await self._persist_central_state(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                tool_name=tool_name,
                target=target_key or target,
                fingerprint=fingerprint,
                args=adjusted_args,
                status="planned",
                reason=strategy or "planned by agent",
                extra_properties=lifecycle_properties,
            )

            if stop_reason:
                skipped = ToolResult(success=False, output=stop_reason, error=stop_reason)
                skipped_dict = self._result_to_dict(skipped)
                status, outcome, next_step = self._classify_execution_outcome(
                    tool_name,
                    skipped_dict,
                    coalesced=False,
                )
                self._record_tool_attempt(tool_name, adjusted_args, fingerprint, skipped)
                await self._persist_insight_memory(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    tool_name=tool_name,
                    target=target,
                    fingerprint=fingerprint,
                    args=adjusted_args,
                    result_dict=skipped_dict,
                )
                await self._persist_central_memory(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    tool_name=tool_name,
                    target=target_key or target,
                    fingerprint=fingerprint,
                    args=adjusted_args,
                    result_dict=skipped_dict,
                    status_override=status,
                    reason_override=self._trim_text(stop_reason, limit=280),
                    extra_properties={
                        **lifecycle_properties,
                        "outcome": outcome,
                        "next_step": next_step,
                    },
                )
                await self._persist_blackboard_tool_result(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    tool_name=tool_name,
                    target=target_key or target,
                    fingerprint=fingerprint,
                    args=adjusted_args,
                    result_dict=skipped_dict,
                    status=status,
                    outcome=outcome,
                    next_step=next_step,
                    strategy=strategy,
                )
                if self.event_manager:
                    await self.event_manager.emit_tool_complete(tool_name, skipped, str(scan_id))
                return skipped_dict

            skip_reason = self._should_skip_tool_call(tool_name, adjusted_args, fingerprint)
            if skip_reason:
                skipped = ToolResult(success=False, output=skip_reason, error=skip_reason)
                skipped_dict = self._result_to_dict(skipped)
                status, outcome, next_step = self._classify_execution_outcome(
                    tool_name,
                    skipped_dict,
                    coalesced=False,
                )
                self._record_tool_attempt(tool_name, adjusted_args, fingerprint, skipped)
                await self._persist_insight_memory(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    tool_name=tool_name,
                    target=target,
                    fingerprint=fingerprint,
                    args=adjusted_args,
                    result_dict=skipped_dict,
                )
                await self._persist_central_memory(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    tool_name=tool_name,
                    target=target_key or target,
                    fingerprint=fingerprint,
                    args=adjusted_args,
                    result_dict=skipped_dict,
                    status_override=status,
                    reason_override=self._trim_text(skip_reason, limit=280),
                    extra_properties={
                        **lifecycle_properties,
                        "outcome": outcome,
                        "next_step": next_step,
                    },
                )
                await self._persist_blackboard_tool_result(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    tool_name=tool_name,
                    target=target_key or target,
                    fingerprint=fingerprint,
                    args=adjusted_args,
                    result_dict=skipped_dict,
                    status=status,
                    outcome=outcome,
                    next_step=next_step,
                    strategy=strategy,
                )
                if self.event_manager:
                    await self.event_manager.emit_tool_complete(tool_name, skipped, str(scan_id))
                return skipped_dict

            active_peer = await self._central_memory_service.find_active_peer_execution(
                session=session,
                scan_id=scan_id,
                fingerprint=fingerprint,
                requesting_agent_id=self.agent_id,
            )
            if active_peer:
                peer_id = str(active_peer.get("agent_id") or "peer")
                note = (
                    f"Coalesced planning: peer agent {peer_id} is already executing this exact {tool_name} command. "
                    "Wait for peer result or pivot scope; do not infer vulnerability or non-vulnerability from this coalescing event."
                )
                coalesced_result = ToolResult(
                    success=True,
                    output=note,
                    data={
                        "coalesced": True,
                        "peer_agent_id": peer_id,
                        "peer_status": str(active_peer.get("status") or "running"),
                    },
                )
                coalesced_dict = self._result_to_dict(coalesced_result)
                status, outcome, next_step = self._classify_execution_outcome(
                    tool_name,
                    coalesced_dict,
                    coalesced=True,
                )
                self._record_tool_attempt(tool_name, adjusted_args, fingerprint, coalesced_result)
                await self._persist_insight_memory(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    tool_name=tool_name,
                    target=target,
                    fingerprint=fingerprint,
                    args=adjusted_args,
                    result_dict=coalesced_dict,
                )
                await self._persist_central_memory(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    tool_name=tool_name,
                    target=target_key or target,
                    fingerprint=fingerprint,
                    args=adjusted_args,
                    result_dict=coalesced_dict,
                    status_override=status,
                    reason_override=self._trim_text(note, limit=280),
                    extra_properties={
                        **lifecycle_properties,
                        "outcome": outcome,
                        "next_step": next_step,
                        "coalesced": True,
                        "coalesced_peer_agent_id": peer_id,
                    },
                )
                await self._persist_blackboard_tool_result(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    tool_name=tool_name,
                    target=target_key or target,
                    fingerprint=fingerprint,
                    args=adjusted_args,
                    result_dict=coalesced_dict,
                    status=status,
                    outcome=outcome,
                    next_step=next_step,
                    strategy=strategy,
                )
                if self.event_manager:
                    await self.event_manager.emit_tool_complete(tool_name, coalesced_result, str(scan_id))
                return coalesced_dict

            await self._persist_central_state(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                tool_name=tool_name,
                target=target_key or target,
                fingerprint=fingerprint,
                args=adjusted_args,
                status="running",
                reason=backoff_note or strategy or "executing tool",
                extra_properties=lifecycle_properties,
            )

            # Emit tool start only for actual executions.
            if self.event_manager:
                await self.event_manager.emit_tool_start(tool_name, target, self.agent_id, str(scan_id))

            # Execute tool with concurrency limits for heavy scanners.
            execution_args = {**adjusted_args, "agent_id": self.agent_id, "scan_id": str(scan_id)}
            result, execution_meta = await self._execute_tool_with_limits(
                tool_name,
                tool,
                execution_args,
                dedupe_key=fingerprint,
            )
            was_coalesced = bool((execution_meta or {}).get("coalesced", False))

            if backoff_note and hasattr(result, "output") and result.output:
                result.output = f"{backoff_note}\n\n{result.output}"
            
            # Normalize result
            if hasattr(result, 'dict'):
                result_dict = result.dict()
            elif isinstance(result, dict):
                result_dict = result
            else:
                result_dict = {"success": True, "output": str(result), "data": {}}

            if was_coalesced:
                data = result_dict.get("data")
                if not isinstance(data, dict):
                    data = {}
                data["coalesced"] = True
                data["coalesced_reason"] = "inflight duplicate executed by peer in scheduler"
                result_dict["data"] = data

            status, outcome, next_step = self._classify_execution_outcome(
                tool_name,
                result_dict,
                coalesced=was_coalesced,
            )
            self._record_tool_attempt(tool_name, adjusted_args, fingerprint, result_dict)
            await self._persist_insight_memory(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                tool_name=tool_name,
                target=target,
                fingerprint=fingerprint,
                args=adjusted_args,
                result_dict=result_dict,
            )
            await self._persist_central_memory(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                tool_name=tool_name,
                target=target_key or target,
                fingerprint=fingerprint,
                args=adjusted_args,
                result_dict=result_dict,
                status_override=status,
                reason_override=self._trim_text(str(result_dict.get("error") or result_dict.get("output") or ""), limit=280),
                extra_properties={
                    **lifecycle_properties,
                    "outcome": outcome,
                    "next_step": next_step,
                    "coalesced": was_coalesced,
                },
            )
            await self._persist_blackboard_tool_result(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                tool_name=tool_name,
                target=target_key or target,
                fingerprint=fingerprint,
                args=adjusted_args,
                result_dict=result_dict,
                status=status,
                outcome=outcome,
                next_step=next_step,
                strategy=strategy,
            )
            
            # Emit completion
            if self.event_manager:
                event_result = result
                if not isinstance(event_result, ToolResult):
                    event_result = ToolResult(
                        success=bool(result_dict.get("success")),
                        output=str(result_dict.get("output") or ""),
                        data=result_dict.get("data") if isinstance(result_dict.get("data"), dict) else {},
                        error=result_dict.get("error"),
                    )
                await self.event_manager.emit_tool_complete(tool_name, event_result, str(scan_id))
                
            return result_dict
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            failure = ToolResult(success=False, output=f"Error: {e}", error=str(e))
            fingerprint = self._fingerprint_tool_call(tool_name, args)
            failure_dict = self._result_to_dict(failure)
            status, outcome, next_step = self._classify_execution_outcome(
                tool_name,
                failure_dict,
                coalesced=False,
            )
            self._record_tool_attempt(tool_name, args, fingerprint, failure)
            await self._persist_insight_memory(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                tool_name=tool_name,
                target=target,
                fingerprint=fingerprint,
                args=args,
                result_dict=failure_dict,
            )
            await self._persist_central_memory(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                tool_name=tool_name,
                target=target_key or target,
                fingerprint=fingerprint,
                args=args,
                result_dict=failure_dict,
                status_override=status,
                reason_override=self._trim_text(str(e), limit=280),
                extra_properties={
                    "iteration": self._current_iteration,
                    "strategy": strategy,
                    "outcome": outcome,
                    "next_step": next_step,
                },
            )
            await self._persist_blackboard_tool_result(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                tool_name=tool_name,
                target=target_key or target,
                fingerprint=fingerprint,
                args=args,
                result_dict=failure_dict,
                status=status,
                outcome=outcome,
                next_step=next_step,
                strategy=strategy,
            )
            if self.event_manager:
                await self.event_manager.emit_tool_complete(tool_name, failure, str(scan_id))
            return failure_dict

    def _build_tool_history_content(self, result: Dict[str, Any]) -> str:
        """
        Include tool output plus compact structured fields to improve agent visibility
        without exploding token usage.
        """
        output = str(result.get("output") or "").strip()
        if len(output) > 3500:
            output = output[:3497] + "..."

        evidence_lines = self._extract_key_evidence(result, output)

        data = result.get("data")
        parts: List[str] = []
        if output:
            parts.append(output)
        if evidence_lines:
            evidence_block = "\n".join(f"- {line}" for line in evidence_lines[:6])
            parts.append(f"[tool_evidence]\n{evidence_block}\n[/tool_evidence]")

        if not isinstance(data, dict) or not data:
            return "\n\n".join(parts).strip()

        preferred_keys = (
            "exit_code",
            "vulnerable",
            "total_found",
            "summary",
            "url",
            "target_url",
            "status",
            "command",
        )
        compact: Dict[str, Any] = {}
        for key in preferred_keys:
            if key in data:
                compact[key] = data[key]

        if not compact:
            for key, value in data.items():
                if len(compact) >= 3:
                    break
                if isinstance(value, (str, int, float, bool)):
                    compact[key] = value

        if not compact:
            return output

        compact_json = json.dumps(compact, sort_keys=True, default=str, separators=(",", ":"))
        if len(compact_json) > 700:
            compact_json = compact_json[:697] + "..."

        data_tail = f"[tool_data]{compact_json}[/tool_data]"
        parts.append(data_tail)
        return "\n\n".join(parts).strip()

    def _extract_key_evidence(self, result: Dict[str, Any], output: str) -> List[str]:
        """
        Extract a small evidence set that is easy for the LLM to plan against.
        """
        evidence: List[str] = []
        if not output:
            return evidence

        important = re.compile(
            r"\b(vulnerab|cve-|open|found|severity|critical|high|timeout|timed out|error|failed|"
            r"status|title|database|privilege|payload|login|rce|sqli|xss|200|301|302|403)\b",
            re.IGNORECASE,
        )
        seen = set()
        for raw_line in output.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue
            if len(line) > 180:
                line = line[:177] + "..."
            if important.search(line) and line.lower() not in seen:
                evidence.append(line)
                seen.add(line.lower())
            if len(evidence) >= 6:
                break

        if evidence:
            return evidence

        # Fallback: first meaningful lines.
        for raw_line in output.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue
            if len(line) > 180:
                line = line[:177] + "..."
            if line.lower() in seen:
                continue
            evidence.append(line)
            seen.add(line.lower())
            if len(evidence) >= 3:
                break
        return evidence

    async def _execute_tool_with_limits(
        self,
        tool_name: str,
        tool: Any,
        execution_args: Dict[str, Any],
        dedupe_key: Optional[str] = None,
    ) -> tuple[Any, Dict[str, Any]]:
        if self._tool_scheduler is not None:
            scheduled = await self._tool_scheduler.execute(
                tool_name=tool_name,
                coro_factory=lambda: tool.execute(**execution_args),
                dedupe_key=dedupe_key,
            )
            return scheduled.result, {"coalesced": bool(scheduled.coalesced), "scheduler": "queue"}

        per_tool_semaphore = self._tool_semaphores.get(tool_name)
        should_limit_global = tool_name in self._limited_heavy_tools and self._global_tool_semaphore is not None

        if not per_tool_semaphore and not should_limit_global:
            return await tool.execute(**execution_args), {"coalesced": False, "scheduler": "direct"}

        async with AsyncExitStack() as stack:
            if should_limit_global:
                await stack.enter_async_context(self._global_tool_semaphore)
            if per_tool_semaphore:
                await stack.enter_async_context(per_tool_semaphore)
            return await tool.execute(**execution_args), {"coalesced": False, "scheduler": "semaphore"}
