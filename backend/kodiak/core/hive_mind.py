import asyncio
from datetime import datetime
from typing import Dict, Optional, Set

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from kodiak.database.models import AgentLog


class CommandLock:
    """
    The Hive Mind's synchronization primitive.
    Prevents multiple agents from running the same command string simultaneously.
    """

    def __init__(self):
        self._running_commands: Dict[str, asyncio.Future] = {}
        self._completed_commands: Dict[str, str] = {}  # Naive in-memory cache for now
        self._subscribers: Dict[str, Set[str]] = {}  # command -> set of agent_ids

    def is_running(self, command_str: str) -> bool:
        return command_str in self._running_commands

    async def acquire(self, command_str: str, agent_id: str) -> bool:
        """
        Try to acquire the lock for a command.
        Returns True if acquired (you are the leader).
        Returns False if already running (you should wait).
        """
        if command_str in self._running_commands:
            if command_str not in self._subscribers:
                self._subscribers[command_str] = set()
            self._subscribers[command_str].add(agent_id)
            logger.info(f"Agent {agent_id} subscribing to existing command: {command_str}")
            return False

        # Create a future that will be set when the command completes
        self._running_commands[command_str] = asyncio.Future()
        self._subscribers[command_str] = {agent_id}
        logger.info(f"Agent {agent_id} acquired lock for: {command_str}")
        return True

    async def wait_for_result(self, command_str: str) -> str:
        """
        Wait for an existing command to finish and return its output.
        """
        if command_str in self._completed_commands:
            return self._completed_commands[command_str]

        if command_str not in self._running_commands:
            raise ValueError(f"Command {command_str} is not running or cached.")

        logger.info(f"Waiting for result of: {command_str}")
        return await self._running_commands[command_str]

    async def release(self, command_str: str, output: str):
        """
        Release the lock and notify all subscribers.
        """
        if command_str not in self._running_commands:
            return

        future = self._running_commands[command_str]
        
        # Cache the result
        self._completed_commands[command_str] = output
        
        # Notify waiters
        if not future.done():
            future.set_result(output)
            
        # Cleanup
        del self._running_commands[command_str]
        subscribers = self._subscribers.pop(command_str, set())
        logger.info(f"Released lock for {command_str}. Notified {len(subscribers)} agents.")

    def get_cached_result(self, command_str: str) -> Optional[str]:
        """
        Check if we already have a result for this command.
        """
        # TODO: checking timestamp/expiry would be good here
        return self._completed_commands.get(command_str)

# Global Hive Mind Instance
hive_mind = CommandLock()
