from typing import Any, Dict, List, Optional
import json
from kodiak.core.config import settings

class KodiakAgent:
    """
    The Brain. 
    Decoupled from the loop. It just takes state in, and outputs actions.
    Enhanced with dynamic skill loading capabilities and EventManager integration.
    Integrates with Hive Mind for state synchronization across agents.
    """
    def __init__(self, agent_id: str, tool_inventory, event_manager, model_name: str = None, session: Any = None, role: str = "generalist", project_id: Any = None, skills: Optional[List[str]] = None):
        self.agent_id = agent_id
        self.model_name = model_name or settings.llm_model
        self.session = session
        self.role = role
        self.project_id = project_id
        self.tool_inventory = tool_inventory
        self.event_manager = event_manager
        self.inbox: List[Dict[str, Any]] = [] # Priority Message Queue
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
            print(f"Warning: Failed to load skills: {e}")
            self.skills_knowledge = ""

    def add_skills(self, skill_names: List[str]):
        """Add additional skills to the agent"""
        self.loaded_skills.extend(skill_names)
        self.loaded_skills = list(set(self.loaded_skills))  # Remove duplicates
        self._load_agent_skills()

    def receive_message(self, content: str, sender: str = "Commander"):
        """
        Push a priority message to the inbox.
        """
        self.inbox.append({"sender": sender, "content": content, "timestamp": "now"})
        
    async def think(self, history: List[Dict[str, Any]], allowed_tools: List[str] = None, system_prompt: str = None) -> Any:
        """
        Ask the LLM what to do next given the conversation history.
        Returns the full response object from LiteLLM (which contains tool_calls).
        
        :param allowed_tools: List of tool names to expose to the LLM. If None, uses all.
        :param system_prompt: Custom system prompt for the current phase.
        """
        from litellm import acompletion
        import os

        # 0. SOFT INTERRUPT CHECK
        if self.inbox:
            # If we have priority messages, we override the normal flow.
            # We inject the message as a "System Override" to force attention.
            priority_msg = self.inbox.pop(0) # Process FIFO
            history.append({
                "role": "user", 
                "content": f"[PRIORITY INTERRUPT FROM {priority_msg['sender']}]: {priority_msg['content']}\n"
                           f"DROP CURRENT PLAN AND ADDRESS THIS IMMEDIATELY."
            })

        # 1. Load available tools from inventory
        tools = self._prepare_tools(allowed_tools)
        
        # 2. Rolling Summaries: Compress history if too long
        optimized_history = await self._summarize_history(history)
        
        # 3. Context Injection (The Blackboard)
        context_str = ""
        if self.session and self.project_id:
            context_str = await self._load_context(self.session, self.project_id)

        # 4. Build comprehensive system prompt
        system_content = self._build_system_prompt(system_prompt, context_str)
        
        system_msg = {
            "role": "system",
            "content": system_content
        }
        
        # Prepare messages
        messages = [system_msg] + optimized_history
        
        # Call LLM
        model = self.model_name or "gpt-3.5-turbo" 
        
        # Using OpenAI-compatible tool calling
        response = await acompletion(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        
        return response.choices[0].message

    def _build_system_prompt(self, custom_prompt: str = None, context_str: str = "") -> str:
        """Build comprehensive system prompt including skills and context"""
        
        # Base prompt based on role
        if custom_prompt:
            base_prompt = custom_prompt
        elif self.role == "scout":
            base_prompt = (
                "You are a SCOUT AGENT specialized in reconnaissance and enumeration. "
                "Your primary directive is OBSERVATION and DISCOVERY. "
                "You are methodical and thorough. You map the attack surface systematically. "
                "Voice: Tactical, observant, precise. Report findings clearly."
            )
        elif self.role == "attacker":
            base_prompt = (
                "You are an ATTACKER AGENT specialized in exploitation and validation. "
                "Your directive is PENETRATION and PROOF-OF-CONCEPT development. "
                "You are aggressive but precise. When you identify vulnerabilities, you validate them with working exploits. "
                "Voice: Technical, confident, results-focused. 'Target acquired', 'Exploit confirmed'."
            )
        elif self.role == "manager":
            base_prompt = (
                "You are the MISSION MANAGER responsible for strategy and coordination. "
                "Your directive is ORCHESTRATION and HIGH-LEVEL PLANNING. "
                "You assign tasks to specialized agents and analyze the overall security posture. "
                "Voice: Strategic, commanding, analytical. 'Directing operations', 'Analyzing attack surface'."
            )
        else:
            base_prompt = (
                "You are KODIAK, an advanced autonomous penetration testing agent. "
                "Your goal is to systematically assess security through reconnaissance, enumeration, and vulnerability validation. "
                "You are methodical, thorough, and focused on actionable results."
            )

        # Combine all components
        full_prompt = base_prompt + "\n\n"
        
        # Add skills knowledge if available
        if self.skills_knowledge:
            full_prompt += self.skills_knowledge + "\n"
        
        # Add operational guidelines
        full_prompt += (
            "OPERATIONAL GUIDELINES:\n"
            "- Use tools systematically and interpret results carefully\n"
            "- Validate findings with multiple techniques when possible\n"
            "- Document discoveries in the knowledge graph\n"
            "- Coordinate with other agents to avoid duplicate work\n"
            "- Focus on high-impact vulnerabilities and clear proof-of-concepts\n\n"
        )
        
        # Add context if available
        if context_str:
            full_prompt += context_str + "\n"
        
        # Add efficiency guidelines
        full_prompt += (
            "EFFICIENCY RULES:\n"
            "- Provide concise, actionable responses\n"
            "- Always call appropriate tools or provide final summaries\n"
            "- Use your specialized skills to guide tool selection and payload crafting\n"
        )
        
        return full_prompt

    def _prepare_tools(self, allowed_tools: List[str] = None) -> List[Dict[str, Any]]:
        """Prepare tool definitions for LLM using the injected tool inventory"""
        available_tools = []
        
        # Get all tools from inventory
        all_tools = self.tool_inventory.list_tools()
        
        # Filter tools if allowed_tools is specified
        if allowed_tools:
            filtered_tools = {name: desc for name, desc in all_tools.items() if name in allowed_tools}
        else:
            filtered_tools = all_tools
        
        # Convert to OpenAI tool format
        for tool_name, tool_desc in filtered_tools.items():
            tool_instance = self.tool_inventory.get(tool_name)
            if tool_instance:
                available_tools.append(tool_instance.to_openai_schema())
        
        return available_tools

    async def _load_context(self, session: Any, project_id: Any) -> str:
        """
        Queries the Blackboard (DB) for facts relevant to this project.
        Injects:
        - Known Nodes (Assets)
        - Confirmed Findings
        - Recent Attempts (Tool Executions)
        """
        from kodiak.database.models import Node, Finding, Attempt
        from sqlmodel import select
        
        if not session or not project_id:
            return "CONTEXT: No project context available (offline mode)\n"
            
        context_str = "CURRENT PROJECT CONTEXT:\n"
        
        try:
            # 1. Fetch Key Nodes (Limit 20 recent)
            stmt_nodes = select(Node).where(Node.project_id == project_id).limit(20)
            result = await session.execute(stmt_nodes)
            nodes = result.scalars().all()
            
            if nodes:
                context_str += "DISCOVERED ASSETS:\n"
                for node in nodes:
                    context_str += f"  - {node.type}: {node.name}\n"
                context_str += "\n"
            
            # 2. Fetch Recent Findings
            stmt_findings = select(Finding).where(Finding.node_id.in_([n.id for n in nodes])).limit(10)
            result = await session.execute(stmt_findings)
            findings = result.scalars().all()
            
            if findings:
                context_str += "CONFIRMED VULNERABILITIES:\n"
                for finding in findings:
                    context_str += f"  - [{finding.severity}] {finding.title}\n"
                context_str += "\n"
            
            # 3. Fetch Recent Attempts (to avoid duplication)
            stmt_attempts = select(Attempt).where(Attempt.project_id == project_id).limit(10)
            result = await session.execute(stmt_attempts)
            attempts = result.scalars().all()
            
            if attempts:
                context_str += "RECENT TOOL EXECUTIONS:\n"
                for attempt in attempts:
                    context_str += f"  - {attempt.tool} on {attempt.target}: {attempt.status}\n"
                context_str += "\n"
                
        except Exception as e:
            context_str += f"Error loading context: {str(e)}\n"
        
        return context_str

    async def _summarize_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Compress conversation history if it gets too long.
        Keep recent messages and summarize older ones.
        """
        MAX_MESSAGES = 20
        
        if len(history) <= MAX_MESSAGES:
            return history
        
        # Keep the most recent messages
        recent_messages = history[-MAX_MESSAGES:]
        
        # TODO: Implement actual summarization of older messages
        # For now, just truncate
        return recent_messages

    async def act(self, tool_name: str, args: Dict[str, Any], session: Any = None, project_id: Any = None, task_id: Any = None) -> Any:
        """
        Execute a tool action through the inventory system with proper error handling.
        """
        tool = self.tool_inventory.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found in inventory"}
        
        try:
            # Emit tool start event
            await self.event_manager.emit_tool_start(
                tool_name=tool_name,
                target=args.get('target', 'unknown'),
                agent_id=self.agent_id,
                scan_id=project_id
            )
            
            # Execute the tool
            result = await tool.run(args, context={
                "agent_id": self.agent_id,
                "session": session,
                "project_id": project_id,
                "task_id": task_id
            })
            
            # Emit tool completion event
            await self.event_manager.emit_tool_complete(
                tool_name=tool_name,
                result=result,
                scan_id=project_id
            )
            
            return result.dict() if hasattr(result, 'dict') else result
            
        except Exception as e:
            # Create error result for event emission
            error_result = type('ErrorResult', (), {
                'success': False,
                'error': str(e),
                'output': None,
                'data': None
            })()
            
            # Emit tool completion event with error
            await self.event_manager.emit_tool_complete(
                tool_name=tool_name,
                result=error_result,
                scan_id=project_id
            )
            
            return {"error": f"Tool execution failed: {str(e)}"}

    async def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Execute tool with proper error handling and consistent naming.
        This method ensures tool names are validated against the inventory.
        """
        if tool_name not in self.available_tools:
            return {"error": f"Tool {tool_name} not found in available tools: {self.available_tools}"}
        
        return await self.act(
            tool_name=tool_name,
            args=kwargs,
            session=self.session,
            project_id=self.project_id
        )

    def get_skill_recommendations(self, target_info: Dict[str, Any]) -> List[str]:
        """Get skill recommendations based on target information"""
        try:
            from kodiak.skills import skill_loader
            return skill_loader.suggest_skills_for_target(target_info)
        except Exception:
            return []
