import asyncio
from datetime import datetime
from typing import Dict, Optional, Set

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from kodiak.database.models import CommandCache
from kodiak.database.engine import engine

class CommandLock:
    """
    The Hive Mind's synchronization primitive.
    Prevents multiple agents from running the same command string simultaneously.
    Uses DB for long-term caching and memory for active lock coordination.
    """

    def __init__(self):
        self._running_commands: Dict[str, asyncio.Future] = {}
        # We don't keep long-term cache in memory anymore, we use DB.
        # But we might keep a short-term LRU if needed. For now, DB is authoritative.
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
        if command_str not in self._running_commands:
            # Maybe it finished just before we called this? Check Cache.
            cached = await self.get_cached_result(command_str)
            if cached:
                return cached
            raise ValueError(f"Command {command_str} is not running or cached.")

        logger.info(f"Waiting for result of: {command_str}")
        return await self._running_commands[command_str]

    async def release(self, command_str: str, output: str):
        """
        Release the lock, save to DB, and notify all subscribers.
        """
        if command_str not in self._running_commands:
            return

        future = self._running_commands[command_str]
        
        # 1. Save to Database (Persist the knowledge)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                # Naive normalization of key. TODO: better key parsing if command_hash isn't just the key
                # Assuming command_str IS the key we want to store.
                # In base.py we construct it as "tool_name:json_args".
                parts = command_str.split(":", 1)
                tool_name = parts[0]
                args_json = parts[1] if len(parts) > 1 else "{}"
                
                cache_entry = CommandCache(
                    command_hash=command_str,
                    tool_name=tool_name,
                    args_json=args_json,
                    output=output
                )
                session.add(cache_entry)
                await session.commit()
                logger.info(f"Persisted result for {command_str} to Hive Mind (DB).")
        except Exception as e:
            logger.error(f"Failed to persist {command_str} result to DB: {e}")
        
        # 2. Notify waiters (The subscribers)
        if not future.done():
            future.set_result(output)
            
        # 3. Cleanup Memory
        del self._running_commands[command_str]
        subscribers = self._subscribers.pop(command_str, set())
        logger.info(f"Released lock for {command_str}. Notified {len(subscribers)} agents.")

    async def get_cached_result(self, command_str: str) -> Optional[str]:
        """
        Check if we already have a result for this command in the DB.
        """
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                statement = select(CommandCache).where(CommandCache.command_hash == command_str)
                result = await session.exec(statement)
                entry = result.first()
                if entry:
                    logger.info(f"Hive Mind Cache Hit: {command_str}")
                    return entry.output
        except Exception as e:
            logger.warning(f"Hive Mind Cache Lookup Error: {e}")
            return None
        return None

# Global Hive Mind Instance
hive_mind = CommandLock()
