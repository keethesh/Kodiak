import asyncio
import os
import shutil
from abc import ABC, abstractmethod
from typing import AsyncGenerator

from loguru import logger
from pydantic import BaseModel

# Placeholder for settings import if needed for Docker config
# from kodiak.core.config import settings


class CommandResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class ServiceExecutor(ABC):
    @abstractmethod
    async def run_command(
        self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> CommandResult:
        """Run a command to completion."""
        pass

    @abstractmethod
    async def stream_command(
        self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> AsyncGenerator[str, None]:
        """Stream output line by line."""
        pass


class LocalExecutor(ServiceExecutor):
    async def run_command(
        self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> CommandResult:
        logger.info(f"LocalExec: {' '.join(command)}")
        
        # Merge current env with provided env
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=full_env,
        )
        
        stdout, stderr = await process.communicate()
        
        return CommandResult(
            exit_code=process.returncode or 1,
            stdout=stdout.decode().strip(),
            stderr=stderr.decode().strip(),
        )

    async def stream_command(
        self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> AsyncGenerator[str, None]:
        logger.info(f"LocalExec Stream: {' '.join(command)}")
        
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=full_env,
        )

        if process.stdout:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                yield line.decode()
        
        await process.wait()


class DockerExecutor(ServiceExecutor):
    def __init__(self, image: str = "kalilinux/kali-rolling"):
        self.image = image
        # TODO: Initialize Docker client here
        # self.client = docker.from_env()

    async def run_command(
        self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> CommandResult:
        logger.info(f"DockerExec ({self.image}): {' '.join(command)}")
        # Placeholder implementation
        # In a real impl, this would use aio-docker or thread-pool wrapped docker-py
        return CommandResult(exit_code=0, stdout="Docker not fully implemented yet", stderr="")

class MockExecutor(ServiceExecutor):
    async def run_command(
        self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> CommandResult:
        cmd_str = " ".join(command)
        logger.info(f"MockExec: {cmd_str}")
        
        # HARDCODED: Simulated Nmap Output for verification purposes
        if "nmap" in command:
            # Simulate a brief delay to test concurrency/locking
            await asyncio.sleep(2)
            stdout = (
                "Starting Nmap 7.94 ( https://nmap.org ) at 2024-01-01 12:00 UTC\n"
                "Nmap scan report for 192.168.1.1\n"
                "Host is up (0.001s latency).\n"
                "PORT     STATE SERVICE\n"
                "22/tcp   open  ssh\n"
                "80/tcp   open  http\n"
                "443/tcp  open  https\n"
                "Nmap done: 1 IP address (1 host up) scanned in 2.05 seconds"
            )
            return CommandResult(exit_code=0, stdout=stdout, stderr="")
            
        return CommandResult(exit_code=0, stdout=f"Mock output for: {cmd_str}", stderr="")

    async def stream_command(
        self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> AsyncGenerator[str, None]:
        yield f"Mock stream for {' '.join(command)}"


def get_executor(mode: str = "local") -> ServiceExecutor:
    if mode == "docker":
        return DockerExecutor()
    if mode == "mock":
        return MockExecutor()
    return LocalExecutor()
