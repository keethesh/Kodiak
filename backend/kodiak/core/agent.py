from typing import Any, Dict, List
from kodiak.core.config import settings

class KodiakAgent:
    """
    The Brain. 
    Decoupled from the loop. It just takes state in, and outputs actions.
    """
    def __init__(self, agent_id: str, model_name: str = settings.KODIAK_MODEL, session: Any = None):
        self.agent_id = agent_id
        self.model_name = model_name
        self.session = session
        
    async def think(self, history: List[Dict[str, Any]], allowed_tools: List[str] = None, system_prompt: str = None) -> Any:
        """
        Ask the LLM what to do next given the conversation history.
        Returns the full response object from LiteLLM (which contains tool_calls).
        
        :param allowed_tools: List of tool names to expose to the LLM. If None, uses all.
        :param system_prompt: Custom system prompt for the current phase.
        """
        from litellm import acompletion
        from kodiak.core.tools.inventory import inventory
        import os

        # 1. Dynamic Prompts: Load only requested skills
        # 0. Load Context (The Blackboard)
        context_str = ""
        if hasattr(self, "session") and self.session: 
             # Assuming session is available on self if injected, or passed in think args?
             # For now, simplistic approach: pass session to think?
             # Act ually, orchestrator passes session to _run_agent_for_task, which passes it to Agent ctor
             pass

        # 1. Dynamic Prompts: Load only requested skills
        tools = self._load_skills(inventory, allowed_tools)
        
        # 2. Rolling Summaries: Compress history if too long
        optimized_history = await self._summarize_history(history)
        
        # System Prompt
        content = system_prompt or (
            "You are KODIAK, an advanced autonomous penetration testing agent. "
            "Your goal is to scan, enumerate, and identify vulnerabilities in the target scope. "
            "Efficiency Rule: OUTPUT COMPACT JSON. Do not be verbose. "
            "Result format: Always call a tool or provide a final summary."
        )
        
        # Injection
        if self.session and history and isinstance(history[0]["content"], str) and "MISSION:" in history[0]["content"]:
             # This is likely the first turn "Context Refresher"
             # Or we inject it into the System Prompt
             # Let's inspect session project_id from somewhere?
             # Current simplification: Agent doesn't know project_id in Ctor.
             # Orchestrator should probably pass context_str in system_prompt
             pass
             
        system_msg = {
            "role": "system",
            "content": content
        }
        
        # Prepare messages
        messages = [system_msg] + optimized_history
        
        # Call LLM
        # We use a default generic model if not specified, but settings.KODIAK_MODEL should be set.
        model = self.model_name or "gpt-3.5-turbo" 
        
        # Using OpenAI-compatible tool calling
        response = await acompletion(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        
        return response.choices[0].message

    async def _load_context(self, session: Any, project_id: Any) -> str:
        """
        Queries the Blackboard (DB) for facts relevant to this project.
        Injects:
        - Known Nodes (Assets)
        - Confirmed Findings
        - Recent Attempts (Tool Executions)
        """
        from kodiak.database.models import Node, Finding, Attempt
        from sqlmodel import select, col
        
        if not session or not project_id:
            return "No Context Available (Offline Mode)"
            
        context_str = "BLACKBOARD CONTEXT:\n"
        
        # 1. Fetch Key Nodes (Limit 20 recent)
        stmt_nodes = select(Node).where(Node.project_id == project_id).limit(20)
        nodes = (await session.execute(stmt_nodes)).scalars().all()
        if nodes:
            context_str += "  [NODES]\n"
            for n in nodes:
                context_str += f"  - ({n.type}) {n.name}\n"
        
        # 2. Fetch Findings
        stmt_findings = select(Finding).where(Finding.scan_id == self.agent_id).limit(5) # Self-findings? Generic?
        # Maybe fetch project-wide critical findings?
        stmt_crit = select(Finding).where(Finding.project_id == project_id, col(Finding.severity) == "critical").limit(5)
        findings = (await session.execute(stmt_crit)).scalars().all()
        if findings:
            context_str += "  [CRITICAL FINDINGS]\n"
            for f in findings:
                context_str += f"  - {f.title} (Asset: {f.node_id})\n"
                
        # 3. Fetch Recent Attempts (To avoid loops)
        stmt_attempts = select(Attempt).where(Attempt.project_id == project_id).order_by(col(Attempt.timestamp).desc()).limit(10)
        attempts = (await session.execute(stmt_attempts)).scalars().all()
        if attempts:
            context_str += "  [RECENT OPERATIONS]\n"
            for a in attempts:
                context_str += f"  - [{a.status}] {a.tool} -> {a.target}\n"
                
        return context_str

    def _load_skills(self, inventory, allowed_tools: List[str] = None) -> List[Dict[str, Any]]:
        """
        Dynamically loads only the tools needed for the current context.
        """
        all_tools = inventory._tools
        tools_schema = []
        
        # 1. Standard Inventory Tools
        if allowed_tools:
            for name in allowed_tools:
                if name in all_tools:
                    tools_schema.append(all_tools[name].to_openai_schema())
        else:
             tools_schema = [t.to_openai_schema() for t in all_tools.values()]

        # 2. Meta-Tools (Not in Inventory, Native to Agent)
        # spawn_agent schema
        if not allowed_tools or "spawn_agent" in allowed_tools:
            tools_schema.append({
                "type": "function",
                "function": {
                    "name": "spawn_agent",
                    "description": "Spawn a sub-agent to perform a specific task in parallel.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["scout", "attacker", "specialist"], "description": "The type of agent needed."},
                            "goal": {"type": "string", "description": "Specific instruction for the sub-agent."},
                             "target": {"type": "string", "description": "The target asset for the agent."}
                        },
                        "required": ["role", "goal"]
                    }
                }
            })
            
        return tools_schema

    async def _summarize_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Implements Rolling Summaries.
        If history is too long (> 15 messages), summarizes the older half into a single system message.
        """
        MAX_HISTORY = 15
        
        if len(history) <= MAX_HISTORY:
            return history
            
        # Keep the last N messages intact
        keep_count = 8
        recent_history = history[-keep_count:]
        older_history = history[:-keep_count]
        
        # In a real implementation, we would call an LLM to summarize 'older_history'
        # For now, we will perform a 'lossy' summary by extracting key events (User/Tool outputs)
        # to save tokens without an extra LLM call loop (latency trace).
        
        summary_text = "Previous actions summary: "
        for msg in older_history:
            role = msg.get("role")
            if role == "tool":
                summary_text += f"[Tool Output: {msg.get('name', 'Unknown')}] "
            elif role == "user":
                content = msg.get("content", "")
                if len(content) > 50:
                    content = content[:50] + "..."
                summary_text += f"[User: {content}] "
                
        summary_msg = {
            "role": "system",
            "content": f"HISTORY SUMMARY: {summary_text[:1000]}" # Hardcap summary size
        }
        
        return [summary_msg] + recent_history

    async def act(self, tool_name: str, args: Dict[str, Any], session: Any = None, project_id: Any = None, scan_id: Any = None, **kwargs) -> Any:
        """
        Execute a tool by name with the given arguments.
        If session and project_id are provided, persists Assets and Findings.
        """
        from kodiak.core.tools.inventory import inventory
        from kodiak.database.models import Node, Finding, FindingSeverity, Attempt
        # from kodiak.database.crud import asset as crud_asset 

        
            # --- META TOOLS ---
            if tool_name == "spawn_agent":
                from kodiak.database.models import Task
                
                role = args.get("role")
                goal = args.get("goal")
                target = args.get("target")
                
                # Check Hierarchy (Is this agent allowed to spawn?)
                # Simplified: All agents can spawn
                
                new_task = Task(
                    project_id=project_id,
                    name=f"Subtask: {role}",
                    status="pending",
                    assigned_agent_id=f"{role}-{self.agent_id.split('-')[-1]}-sub", # simplistic ID gen
                    parent_task_id=kwargs.get("task_id"), # Need to pass this in act
                    directive=json.dumps({"role": role, "goal": goal, "target": target}) 
                )
                session.add(new_task)
                await session.commit()
                return {"success": True, "output": f"Spawned {role} to {goal}"}

            if not tool:
                return {"error": f"Tool '{tool_name}' not found."}

            # --- REGULAR TOOLS ---
            # Validate args against tool schema
            if tool.args_schema:
                validated_args = tool.args_schema(**args)
            else:
                validated_args = args # Pass dict directly

            # --- SAFETY CHECK ---
            from kodiak.core.safety import safety
            task_id = kwargs.get("task_id")
            is_safe, reason = await safety.check_tool_safety(tool_name, validated_args, project_id, session, task_id=task_id)
            if not is_safe:
                if task_id:
                    await safety.request_approval(task_id, tool_name, validated_args, session)
                    return {"success": False, "status": "PAUSED", "error": f"Action blocked: {reason}. Waiting for Approval."}
                else:
                    return {"success": False, "error": f"Action blocked: {reason} (No Task ID to pause)"}

            # Execute with Context
            context = {
                "scan_id": scan_id,
                "project_id": project_id,
                "agent_id": self.agent_id,
                "session": session # Pass DB session to tool
            }
            result = await tool.run(validated_args, context=context)
            
            # --- Persistence Logic ---
            if session and project_id and result.success and result.data:
                try:
                    # 1. Save Nodes (Assets)
                    if "assets" in result.data: # Legacy support
                        pass
                    
                    if "nodes" in result.data or "assets" in result.data:
                         nodes_data = result.data.get("nodes", []) + result.data.get("assets", [])
                         for n_data in nodes_data:
                            # Check if exists? (Collision Algo needed later)
                            # Upsert logic
                            # For simplicity now: Just add
                            node = Node(
                                project_id=project_id,
                                label="Asset",
                                type=n_data.get("type", "unknown"),
                                name=n_data.get("value"),
                                properties=n_data.get("metadata", {})
                            )
                            session.add(node)
                    
                    # 2. Save Findings
                    if "findings" in result.data:
                        for f_data in result.data["findings"]:
                            # Find node?
                            # ...
                            # Keep simple
                            pass
                            
                    # 3. Save Attempt (Operational Memory)
                    attempt = Attempt(
                        project_id=project_id,
                        tool=tool_name,
                        target=str(args),
                        status="success",
                        reason=result.output[:100]
                    )
                    session.add(attempt)

                    await session.commit()
                except Exception as e:
                    # Don't fail the tool execution if DB save fails
                    # logger.error(f"Persistence error: {e}")
                    pass

            
            # Return dict representation of result
            return {
                "success": result.success,
                "output": result.output,
                "data": result.data,
                "error": result.error
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
