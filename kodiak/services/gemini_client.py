"""
Native Gemini client built on `google-genai`.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    from google import genai
    from google.genai import types
    _GENAI_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - exercised only when dependency is missing
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    _GENAI_IMPORT_ERROR = exc

from kodiak.services import llm


@dataclass
class GeminiToolFunction:
    name: str
    arguments: str

    def dict(self) -> Dict[str, Any]:
        return {"name": self.name, "arguments": self.arguments}


@dataclass
class GeminiToolCall:
    id: str
    function: GeminiToolFunction
    type: str = "function"

    def dict(self) -> Dict[str, Any]:
        return {"id": self.id, "type": self.type, "function": self.function.dict()}


@dataclass
class GeminiResponse:
    content: str
    tool_calls: List[GeminiToolCall]
    finish_reason: str = ""


class GeminiClient:
    def __init__(self) -> None:
        self._clients: Dict[str, Any] = {}

    async def generate(
        self,
        *,
        model: str,
        api_key: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        thinking_level: str = "high",
        response_mime_type: Optional[str] = None,
    ) -> GeminiResponse:
        normalized_model = llm.normalize_model_name(model)
        model_id = normalized_model.split("/", 1)[1]
        client = self._get_client(api_key)
        contents = self._convert_messages_to_contents(messages)
        config = self._build_generation_config(
            system_prompt=system_prompt,
            tools=tools or [],
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_level=thinking_level,
            response_mime_type=response_mime_type,
        )

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_id,
            contents=contents,
            config=config,
        )
        return self._parse_response(response)

    def _get_client(self, api_key: str) -> genai.Client:
        self._ensure_library_available()
        key = str(api_key or "").strip()
        if key not in self._clients:
            self._clients[key] = genai.Client(api_key=key)
        return self._clients[key]

    def _ensure_library_available(self) -> None:
        if _GENAI_IMPORT_ERROR is None:
            return
        raise RuntimeError(
            "google-genai is required but not installed. "
            "Install project dependencies and retry (expected package: google-genai)."
        ) from _GENAI_IMPORT_ERROR

    def _build_generation_config(
        self,
        *,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        thinking_level: str,
        response_mime_type: Optional[str],
    ) -> types.GenerateContentConfig:
        self._ensure_library_available()
        function_declarations = self._convert_tools(tools)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=float(temperature),
            max_output_tokens=int(max_tokens),
            thinking_config=types.ThinkingConfig(
                thinking_level=llm.normalize_gemini_thinking_level(thinking_level)
            ),
        )
        if function_declarations:
            config.tools = [types.Tool(function_declarations=function_declarations)]
        if response_mime_type:
            config.response_mime_type = response_mime_type
        return config

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[types.FunctionDeclaration]:
        declarations: List[types.FunctionDeclaration] = []
        for tool in tools:
            function = (tool or {}).get("function") or {}
            name = str(function.get("name") or "").strip()
            if not name:
                continue
            parameters = function.get("parameters") or {"type": "object", "properties": {}}
            declarations.append(
                types.FunctionDeclaration(
                    name=name,
                    description=str(function.get("description") or "").strip(),
                    parameters=parameters,
                )
            )
        return declarations

    def _convert_messages_to_contents(self, messages: List[Dict[str, Any]]) -> List[types.Content]:
        """
        Convert OpenAI-style history to Gemini contents.

        Important:
        - We intentionally DO NOT reconstruct prior function_call/function_response parts from
          history because Gemini requires thought_signature propagation for functionCall parts.
          Reconstructing those parts without the original signature triggers INVALID_ARGUMENT.
        - Instead, prior tool calls/results are flattened into plain text context.
        """
        contents: List[types.Content] = []

        for message in messages:
            role = str(message.get("role") or "").strip().lower()
            if role == "system":
                continue

            if role == "user":
                text = str(message.get("content") or "").strip()
                if text:
                    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
                continue

            if role == "assistant":
                content = str(message.get("content") or "").strip()
                call_lines: List[str] = []
                for call in message.get("tool_calls") or []:
                    call_dict = call if isinstance(call, dict) else {}
                    function = call_dict.get("function") or {}
                    tool_name = str(function.get("name") or "").strip()
                    if not tool_name:
                        continue
                    raw_args = function.get("arguments")
                    if isinstance(raw_args, dict):
                        args_text = json.dumps(raw_args, sort_keys=True, default=str)
                    else:
                        args_text = str(raw_args or "{}").strip()
                    if len(args_text) > 800:
                        args_text = args_text[:797] + "..."
                    call_lines.append(f"[tool_call] {tool_name} args={args_text}")

                combined = content
                if call_lines:
                    call_block = "\n".join(call_lines)
                    combined = f"{combined}\n{call_block}".strip()
                if combined:
                    contents.append(
                        types.Content(role="model", parts=[types.Part.from_text(text=combined)])
                    )
                continue

            if role == "tool":
                tool_content = message.get("content")
                tool_name = str(message.get("name") or "tool_response").strip()
                text = str(tool_content or "").strip()
                if len(text) > 3500:
                    text = text[:3497] + "..."
                flattened = (
                    f"[tool_result] {tool_name}\n"
                    f"{text}"
                ).strip()
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=flattened)],
                    )
                )

        return contents

    def _parse_response(self, response: Any) -> GeminiResponse:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return GeminiResponse(content="", tool_calls=[], finish_reason="empty")

        first = candidates[0]
        finish_reason = str(getattr(first, "finish_reason", "") or "").strip().lower()
        content = getattr(first, "content", None)
        parts = getattr(content, "parts", None) or []

        text_parts: List[str] = []
        tool_calls: List[GeminiToolCall] = []
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())

            function_call = getattr(part, "function_call", None)
            if not function_call:
                continue
            tool_name = str(getattr(function_call, "name", "") or "").strip()
            if not tool_name:
                continue
            raw_args = getattr(function_call, "args", None)
            args_obj = raw_args if isinstance(raw_args, dict) else {}
            args_json = json.dumps(args_obj, sort_keys=True, default=str)
            tool_calls.append(
                GeminiToolCall(
                    id=f"call_{uuid4().hex[:12]}",
                    function=GeminiToolFunction(name=tool_name, arguments=args_json),
                )
            )

        return GeminiResponse(
            content="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )
