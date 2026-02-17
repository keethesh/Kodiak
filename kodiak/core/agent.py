from typing import Any, Dict, List, Optional
import json
import asyncio
import time
from uuid import uuid4, UUID
from dataclasses import dataclass
from loguru import logger

import litellm
from litellm import acompletion

from kodiak.core.config import settings
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
        skills: Optional[List[str]] = None
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
        
        # Use actual tool names from inventory
        self.available_tools = [tool_name for tool_name in self.tool_inventory.list_tools().keys()]
        
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
        max_iterations: int = 25
    ) -> AgentResult:
        """
        Run the full think-act loop.
        
        Returns when:
        - Agent calls complete_scan tool
        - max_iterations reached
        - Error occurs
        """
        logger.info(f"🚀 Agent {self.agent_id} starting run for goal: {goal}")
        
        history = [
            {
                "role": "user", 
                "content": f"Goal: {goal}\nTarget: {target}\n\nBegin your security scan. Use tools systematically. When you have achieved your objective, call the complete_scan tool with a summary of your findings."
            }
        ]
        
        iterations = 0
        findings_count = 0
        
        while iterations < max_iterations:
            iterations += 1
            logger.debug(f"🔄 Iteration {iterations}/{max_iterations}")
            
            # 1. Think
            response = await self.think(history)
            
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
                    
                    # Execute action
                    result = await self.act(
                        tool_name=tool_name,
                        args=args,
                        session=session,
                        project_id=project_id,
                        scan_id=scan_id
                    )
                    
                    # Add tool result to history
                    history.append({
                        "role": "tool",
                        "tool_call_id": clean_id,
                        "content": result.get("output", "")
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
                    "content": "Continue your scan. If you are finished, call the complete_scan tool."
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
            system_prompt = self._build_system_prompt(custom_prompt, context_str)
            
            # Prepare tools
            tools = self._prepare_tools()
            
            # Prepare messages
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add summarized heart of history
            condensed_history = await self._summarize_history(history)
            messages.extend(condensed_history)
            
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
            base_prompt = "You are a SCOUT AGENT specialized in reconnaissance. Methodical and thorough."
        elif self.role == "attacker":
            base_prompt = "You are an ATTACKER AGENT specialized in exploitation. Aggressive but precise."
        else:
            base_prompt = "You are KODIAK, an advanced autonomous penetration testing agent."

        full_prompt = base_prompt + "\n\n"
        
        if self.skills_knowledge:
            full_prompt += "SKILLS KNOWLEDGE:\n" + self.skills_knowledge + "\n\n"
        
        full_prompt += (
            "EXECUTION ENVIRONMENT:\n"
            "All security tools run inside a Kali Docker container. You call the tool and it runs automatically.\n\n"
            "OPERATIONAL GUIDELINES:\n"
            "- Use tools systematically and interpret results carefully\n"
            "- Focus on high-impact vulnerabilities\n"
            "- CALL complete_scan tool when you are finished\n\n"
        )
        
        if context_str:
            full_prompt += context_str + "\n"
        
        return full_prompt

    def _prepare_tools(self, allowed_tools: List[str] = None) -> List[Dict[str, Any]]:
        """Prepare tool definitions for LLM"""
        available_tools = []
        all_tools = self.tool_inventory.list_tools()
        
        filtered_names = allowed_tools if allowed_tools else all_tools.keys()
        
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
        """Keep history within reasonable limits"""
        return history[-15:]

    async def act(
        self, 
        tool_name: str, 
        args: Dict[str, Any], 
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
        
        # Emit tool start
        if self.event_manager:
            await self.event_manager.emit_tool_start(tool_name, target, self.agent_id, str(scan_id))
        
        try:
            # Execute tool
            execution_args = {**args, "agent_id": self.agent_id, "scan_id": str(scan_id)}
            result = await tool.execute(**execution_args)
            
            # Normalize result
            if hasattr(result, 'dict'):
                result_dict = result.dict()
            elif isinstance(result, dict):
                result_dict = result
            else:
                result_dict = {"success": True, "output": str(result), "data": {}}
            
            # Emit completion
            if self.event_manager:
                await self.event_manager.emit_tool_complete(tool_name, result, str(scan_id))
                
            return result_dict
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {"error": str(e), "success": False, "output": f"Error: {e}"}
