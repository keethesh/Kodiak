import json
from typing import Any, Dict, Optional
from uuid import UUID

from loguru import logger
from litellm import acompletion

from kodiak.core.config import settings
from kodiak.database.crud import insight_memory
from kodiak.database.models import InsightMemory
from kodiak.services import llm


class InsightMemoryService:
    """Generates and persists compact LLM-authored tool insights per scan."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._insight_tools = {
            "nmap",
            "nuclei",
            "sqlmap",
            "ffuf",
            "katana",
            "httpx",
            "whatweb",
            "searchsploit",
            "browser_navigate",
            "browser_extract",
            "browser_click",
            "browser_fill",
            "browser_screenshot",
            "terminal_execute",
        }
        self._terminal_fetch_prefixes = ("curl ", "wget ", "http ")

    def should_generate(self, tool_name: str, args: Dict[str, Any]) -> bool:
        if not settings.memory_enabled:
            return False
        if tool_name not in self._insight_tools:
            return False
        if tool_name == "terminal_execute":
            command = " ".join(str(args.get("command", "")).split()).lower()
            return command.startswith(self._terminal_fetch_prefixes)
        return True

    async def generate_and_store(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        tool_name: str,
        target: str,
        fingerprint: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.should_generate(tool_name, args):
            return None
        if not session or not project_id or not scan_id:
            return None

        status = "success" if result.get("success") else "failure"
        result_text = f"{result.get('output', '')}\n{result.get('error', '')}".strip()
        if self._is_timeout_result(result):
            status = "timeout"
        truncated_output = result_text[: settings.memory_output_chars]

        insight_obj = await self._generate_insight(
            tool_name=tool_name,
            target=target,
            args=args,
            status=status,
            output=truncated_output,
        )

        record = InsightMemory(
            project_id=project_id,
            scan_id=scan_id,
            tool=tool_name,
            target=target or "unknown",
            fingerprint=fingerprint,
            status=status,
            insight=insight_obj,
        )

        try:
            await insight_memory.create(session, record)
        except Exception as e:
            error_text = str(e).lower()
            if "no such table" in error_text and "insightmemory" in error_text:
                try:
                    from kodiak.database.engine import init_db

                    await init_db()
                    await insight_memory.create(session, record)
                except Exception as retry_error:
                    logger.warning(f"Failed to persist insight memory after init_db retry: {retry_error}")
            else:
                # Keep scanning even if memory persistence fails.
                logger.warning(f"Failed to persist insight memory: {e}")

        return {
            "tool": tool_name,
            "target": target or "unknown",
            "fingerprint": fingerprint,
            "status": status,
            "insight": insight_obj,
        }

    async def _generate_insight(
        self,
        tool_name: str,
        target: str,
        args: Dict[str, Any],
        status: str,
        output: str,
    ) -> Dict[str, Any]:
        prompt = (
            "<task>\n"
            "Summarize one tool execution into compact scan memory.\n"
            "</task>\n"
            "<output_contract>\n"
            "Return ONLY valid JSON. No markdown. No surrounding prose.\n"
            "Schema:\n"
            "{"
            '"what_was_tested":"string",'
            '"key_observations":["string"],'
            '"confidence":"low|medium|high",'
            '"next_best_actions":["string"],'
            '"do_not_repeat":"string"'
            "}\n"
            "Rules:\n"
            "- Keep key_observations and next_best_actions to max 3 items each.\n"
            "- If unknown, use empty string/array instead of inventing data.\n"
            "</output_contract>\n"
            "<input>\n"
            f"tool={tool_name}\n"
            f"target={target}\n"
            f"status={status}\n"
            f"args={json.dumps(args, sort_keys=True, default=str)}\n"
            f"output={output}\n"
            "</input>\n"
        )

        try:
            provider = llm.infer_provider_from_model(self.model_name)
            api_key = llm.get_api_key_for_provider(provider)

            params = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a precise security scan memory summarizer. "
                            "Follow the output contract exactly and return only valid JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 500,
            }
            if provider in {"gemini", "vertex_ai", "openai"}:
                # Prefer model-side JSON enforcement over prompt-only contracts.
                params["response_format"] = {"type": "json_object"}
            if api_key:
                params["api_key"] = api_key

            response = await acompletion(**params)
            content = response.choices[0].message.content if response and response.choices else ""
            parsed = self._parse_insight_content(content)
            if parsed:
                return parsed
        except Exception as e:
            logger.warning(f"Insight generation failed, using fallback: {e}")

        return self._fallback_insight(tool_name, target, status, output)

    def _parse_insight_content(self, content: Any) -> Optional[Dict[str, Any]]:
        if not content:
            return None
        text = content if isinstance(content, str) else str(content)
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return None

        return {
            "what_was_tested": str(obj.get("what_was_tested", "")).strip(),
            "key_observations": self._normalize_list(obj.get("key_observations")),
            "confidence": self._normalize_confidence(obj.get("confidence")),
            "next_best_actions": self._normalize_list(obj.get("next_best_actions")),
            "do_not_repeat": str(obj.get("do_not_repeat", "")).strip(),
        }

    def _normalize_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(v).strip() for v in value if str(v).strip()]
            return cleaned[:3]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _normalize_confidence(self, value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"low", "medium", "high"}:
            return raw
        return "medium"

    def _fallback_insight(self, tool_name: str, target: str, status: str, output: str) -> Dict[str, Any]:
        do_not_repeat = ""
        if status == "timeout":
            do_not_repeat = "Do not repeat identical command after timeout; reduce intensity first."
        elif status == "failure":
            do_not_repeat = "Do not retry with identical args until root cause changes."

        observation = output[:160].replace("\n", " ").strip()
        if not observation:
            observation = "No structured output."

        return {
            "what_was_tested": f"{tool_name} on {target or 'unknown'}",
            "key_observations": [observation],
            "confidence": "medium",
            "next_best_actions": ["Adjust parameters or pivot tool/target based on last result."],
            "do_not_repeat": do_not_repeat,
        }

    def _is_timeout_result(self, result: Dict[str, Any]) -> bool:
        text = f"{result.get('error', '')} {result.get('output', '')}".lower()
        return "timeout" in text or "timed out" in text
