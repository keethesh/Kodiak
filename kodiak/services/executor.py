import asyncio
import os
import shutil
from abc import ABC, abstractmethod
from typing import AsyncGenerator

from loguru import logger
from pydantic import BaseModel

# Import settings for Docker config if needed
from kodiak.core.config import settings


class CommandResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class ServiceExecutor(ABC):
    @abstractmethod
    async def run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
        cap_add: list[str] | None = None,
    ) -> CommandResult:
        """Run a command to completion.

        ``cap_add`` — optional list of Linux capabilities to add (Docker only).
        Use e.g. ``["NET_RAW", "NET_ADMIN"]`` for tools that require raw sockets
        (nmap -sS/-O, masscan).  Ignored by non-Docker executors.
        """
        pass

    @abstractmethod
    async def stream_command(
        self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> AsyncGenerator[str, None]:
        """Stream output line by line."""
        pass


class LocalExecutor(ServiceExecutor):
    async def run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
        cap_add: list[str] | None = None,
    ) -> CommandResult:
        logger.info(f"LocalExec: {' '.join(command)}")
        
        # Merge current env with provided env
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=full_env,
        )
        
        try:
            stdout, stderr = await process.communicate(input=stdin.encode() if stdin is not None else None)
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
            
        return CommandResult(
            exit_code=process.returncode or 0,
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

        try:
            if process.stdout:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    yield line.decode()
            await process.wait()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise


class DockerExecutor(ServiceExecutor):
    """
    Runs commands inside Docker containers.
    Used when Kodiak runs locally but needs to execute security tools in a containerized environment.
    """
    def __init__(self, image: str = "kalilinux/kali-rolling", entrypoint: str | None = None):
        self.image = image
        self.entrypoint = entrypoint
        logger.info(f"DockerExecutor initialized with image: {self.image}")

    async def run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
        cap_add: list[str] | None = None,
    ) -> CommandResult:
        """
        Execute command inside Docker container.
        Maps the working directory into the container and runs the command.

        ``cap_add`` — optional list of Linux capabilities to add (e.g. ``["NET_RAW", "NET_ADMIN"]``
        for tools that require raw socket access such as nmap -sS/-O).
        """
        # Use absolute path for volume mounting
        work_dir = os.path.abspath(cwd) if cwd else os.getcwd()
        
        # Build docker run command
        docker_cmd = [
            "docker", "run",
            "--rm",  # Remove container after execution
        ]

        # Add only the capabilities that are actually needed instead of --privileged.
        if cap_add:
            for cap in cap_add:
                docker_cmd.extend(["--cap-add", cap])
        
        if stdin is not None:
            docker_cmd.append("-i")
            
        docker_cmd.extend([
            "-v", f"{work_dir}:/workspace",  # Mount working directory
            "-w", "/workspace",  # Set working directory inside container
        ])
        
        # Override entrypoint if specified
        if self.entrypoint is not None:
            docker_cmd.extend(["--entrypoint", self.entrypoint])
        
        # Add environment variables
        if env:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
        
        # Add image and command
        docker_cmd.append(self.image)
        docker_cmd.extend(command)
        
        logger.info(f"DockerExec: {' '.join(docker_cmd)}")
        
        try:
            # Execute docker run command
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdin=asyncio.subprocess.PIPE if stdin is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await process.communicate(input=stdin.encode() if stdin is not None else None)
            except asyncio.CancelledError:
                process.kill()
                await process.wait()
                raise
            
            return CommandResult(
                exit_code=process.returncode or 0,
                stdout=stdout.decode().strip(),
                stderr=stderr.decode().strip(),
            )
            
        except FileNotFoundError:
            # Docker not installed or not in PATH
            error_msg = "Docker is not installed or not available in PATH"
            logger.error(error_msg)
            return CommandResult(
                exit_code=127,
                stdout="",
                stderr=error_msg
            )
        except Exception as e:
            logger.error(f"Docker execution failed: {e}")
            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=str(e)
            )

    async def stream_command(
        self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream command output from Docker container.
        """
        work_dir = os.path.abspath(cwd) if cwd else os.getcwd()
        
        docker_cmd = [
            "docker", "run",
            "--rm",
            "-v", f"{work_dir}:/workspace",
            "-w", "/workspace",
        ]
        
        if env:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
        
        docker_cmd.append(self.image)
        docker_cmd.extend(command)
        
        logger.info(f"DockerExec Stream: {' '.join(docker_cmd)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                if process.stdout:
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        yield line.decode()
                
                await process.wait()
            except asyncio.CancelledError:
                process.kill()
                await process.wait()
                raise
            
        except Exception as e:
            logger.error(f"Docker stream failed: {e}")
            yield f"Error: {str(e)}\n"


class MockExecutor(ServiceExecutor):
    async def run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
        cap_add: list[str] | None = None,
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


async def get_docker_executor(
    preferred_image: str | None = None, 
    fallback_image: str = "kalilinux/kali-rolling",
    fallback_entrypoint: str | None = None
) -> DockerExecutor:
    """
    Returns a DockerExecutor, falling back to fallback_image if the
    preferred image is not accessible (e.g. private registry denied).
    """
    import asyncio

    # Use the provided fallback image (defaulting to kali-rolling if not specified)
    image = preferred_image or fallback_image
    entrypoint = None

    if image != fallback_image:
        # Quick check: try to inspect the image locally first
        try:
            check = await asyncio.create_subprocess_exec(
                "docker", "image", "inspect", image,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await check.wait()
            except asyncio.CancelledError:
                check.kill()
                await check.wait()
                raise
                
            if check.returncode != 0:
                # Not cached locally — try a pull (with short timeout)
                pull = await asyncio.create_subprocess_exec(
                    "docker", "pull", image,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    await asyncio.wait_for(pull.wait(), timeout=15)
                    if pull.returncode != 0:
                        logger.warning(f"Could not pull {image}, falling back to {fallback_image}")
                        image = fallback_image
                        entrypoint = fallback_entrypoint
                except asyncio.TimeoutError:
                    pull.kill()
                    await pull.wait()  # Wait for proper cleanup
                    logger.warning(f"Pull of {image} timed out, falling back to {fallback_image}")
                    image = fallback_image
                    entrypoint = fallback_entrypoint
                except asyncio.CancelledError:
                    pull.kill()
                    await pull.wait()
                    raise
        except Exception as e:
            logger.warning(f"Docker image check failed ({e}), falling back to {fallback_image}")
            image = fallback_image
            entrypoint = fallback_entrypoint

    return DockerExecutor(image=image, entrypoint=entrypoint)

