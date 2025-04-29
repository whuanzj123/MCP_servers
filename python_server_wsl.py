"""
Python Execution MCP Server with WSL2 Docker Integration

This server uses the FastMCP API for reliable initialization
and adds Docker/WSL functionality for Python execution.
"""

import os
import sys
import uuid
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import asyncio
from mcp.server.fastmcp import FastMCP, Context

# Configure logging to stderr for Claude logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Configure the working directory for Python files
ROOT_DIR = Path(__file__).parent.absolute()
PYTHON_FILES_DIR = ROOT_DIR / "python_files"
OUTPUT_DIR = ROOT_DIR / "python_outputs"

# Storage for mapping execution IDs to results
EXECUTION_MAPPING_FILE = OUTPUT_DIR / "execution_mappings.json"

# Docker configuration
DOCKER_IMAGE = "python:3.11-slim"  # Base Python image to use
CONTAINER_WORK_DIR = "/app"  # Working directory inside container
CONTAINER_TIMEOUT = 30  # Default timeout in seconds
CONTAINER_MEMORY_LIMIT = "512m"  # Memory limit per container
CONTAINER_CPU_LIMIT = "1"  # CPU limit (1 core)

# WSL configuration
WSL_DISTRIBUTIONS = ["Ubuntu", ""]  # Empty string means default distribution

# Setup application state
class AppState:
    def __init__(self):
        self.wsl_distro = None
        self.docker_available = False
        self.docker_image_available = False
        self.execution_results = {}

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppState]:
    """Manage application lifecycle with proper initialization"""
    state = AppState()
    logger.info("Starting server initialization")
    
    # Create directories as needed
    PYTHON_FILES_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Load execution results
    try:
        if EXECUTION_MAPPING_FILE.exists():
            with open(EXECUTION_MAPPING_FILE, 'r') as f:
                state.execution_results = json.load(f)
        else:
            with open(EXECUTION_MAPPING_FILE, 'w') as f:
                json.dump({}, f)
    except Exception as e:
        logger.error(f"Error loading execution results: {e}")
    
    # Begin WSL initialization in the background without awaiting it
    import asyncio
    initialization_task = asyncio.create_task(initialize_wsl_docker(state))
    logger.info("WSL/Docker initialization started in background")
    
    try:
        # Yield to allow the server to initialize and start accepting requests
        yield state
    finally:
        # Cleanup on shutdown
        try:
            # Wait for initialization to complete if it's still running
            if not initialization_task.done():
                logger.info("Waiting for background initialization to complete...")
                try:
                    await asyncio.wait_for(initialization_task, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Background initialization timed out during shutdown")
            
            # Save execution results
            with open(EXECUTION_MAPPING_FILE, 'w') as f:
                json.dump(state.execution_results, f, indent=2)
            
            logger.info("Server shutdown complete")
        except Exception as e:
            logger.error(f"Error during server shutdown: {e}")

# Create an MCP server with proper lifespan management
mcp = FastMCP("Python Docker Executor", lifespan=app_lifespan)

async def initialize_wsl_docker(state: AppState):
    """Initialize WSL and Docker in background"""
    try:
        logger.info("Starting WSL/Docker initialization...")
        
        # Find working WSL distro
        state.wsl_distro = await find_working_wsl_distro()
        
        if state.wsl_distro:
            logger.info(f"Using WSL distribution: {state.wsl_distro}")
            
            # Check Docker
            state.docker_available = await check_docker_in_wsl(state.wsl_distro)
            if state.docker_available:
                logger.info("Docker is available in WSL")
                
                # Pre-check for Docker image
                state.docker_image_available = await check_docker_image_exists(state.wsl_distro, DOCKER_IMAGE)
                if not state.docker_image_available:
                    logger.info(f"Docker image {DOCKER_IMAGE} not found, attempting to pull...")
                    state.docker_image_available = await pull_docker_image(state.wsl_distro, DOCKER_IMAGE)
                else:
                    logger.info(f"Docker image {DOCKER_IMAGE} is available")
                
                # Cleanup old containers
                await cleanup_old_containers(state.wsl_distro)
            else:
                logger.warning("Docker is not available in WSL, execution will fail")
        else:
            logger.warning("No working WSL distribution found, execution will likely fail")
        
        logger.info("WSL/Docker initialization completed successfully")
    except Exception as e:
        logger.exception(f"Error initializing WSL/Docker: {e}")

async def test_wsl_connection(distribution: str = "", timeout: int = 5) -> Tuple[bool, str, str]:
    """
    Test connection to a WSL distribution.
    Returns (success, output, error)
    """
    try:
        if distribution:
            cmd = ["wsl", "-d", distribution, "uname", "-a"]
        else:
            cmd = ["wsl", "uname", "-a"]
        
        logger.info(f"Testing WSL connection with command: {' '.join(cmd)}")
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=timeout)
            success = result.returncode == 0
            logger.info(f"WSL test {'succeeded' if success else 'failed'} with exit code {result.returncode}")
            return success, stdout.decode('utf-8').strip(), stderr.decode('utf-8').strip()
        except asyncio.TimeoutError:
            logger.error(f"WSL test command timed out after {timeout} seconds")
            return False, "", f"Command timed out after {timeout} seconds"
    except Exception as e:
        logger.error(f"Error testing WSL connection: {str(e)}")
        return False, "", str(e)

async def find_working_wsl_distro() -> Optional[str]:
    """
    Find a working WSL distribution.
    Returns the distribution name or None if none work.
    """
    logger.info("Finding a working WSL distribution...")
    
    # First, get list of actual distributions
    try:
        result = await asyncio.create_subprocess_exec(
            "wsl", "--list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()
        if result.returncode == 0:
            logger.info(f"Available WSL distributions: {stdout.decode('utf-8')}")
    except Exception as e:
        logger.error(f"Error listing WSL distributions: {str(e)}")
    
    # Try each distribution from our list
    for distro in WSL_DISTRIBUTIONS:
        distro_display = distro if distro else "default"
        logger.info(f"Trying WSL distribution: {distro_display}")
        
        success, output, error = await test_wsl_connection(distro)
        if success:
            logger.info(f"Successfully connected to WSL distribution: {distro_display}")
            logger.info(f"WSL info: {output}")
            return distro
    
    logger.error("Failed to find a working WSL distribution")
    return None

async def run_wsl_command(distro: str, command: List[str], timeout: int = 30) -> Tuple[str, str, int]:
    """
    Run a command in WSL and return stdout, stderr, and exit code.
    """
    try:
        # Prepare WSL command
        distro_arg = ["-d", distro] if distro else []
        wsl_cmd = ["wsl"] + distro_arg + command
        
        logger.info(f"Running WSL command: {' '.join(wsl_cmd)}")
        
        # Execute command
        process = await asyncio.create_subprocess_exec(
            *wsl_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            stdout_text = stdout.decode('utf-8')
            stderr_text = stderr.decode('utf-8')
            
            logger.info(f"WSL command completed with exit code: {process.returncode}")
            
            # Log truncated output for debugging
            if stdout_text:
                stdout_preview = stdout_text[:200] + "..." if len(stdout_text) > 200 else stdout_text
                logger.debug(f"Command stdout: {stdout_preview}")
            if stderr_text:
                logger.warning(f"Command stderr: {stderr_text}")
            
            return stdout_text, stderr_text, process.returncode
        except asyncio.TimeoutError:
            logger.error(f"WSL command timed out after {timeout} seconds")
            return "", f"Command timed out after {timeout} seconds", -1
    except Exception as e:
        logger.error(f"Error running WSL command: {str(e)}")
        return "", f"Error running WSL command: {str(e)}", -1

async def check_docker_in_wsl(distro: str) -> bool:
    """Check if Docker is available in WSL"""
    logger.info("Checking Docker availability in WSL")
    stdout, stderr, exit_code = await run_wsl_command(distro, ["docker", "info"], timeout=5)
    logger.info(f"Docker check result: {'Available' if exit_code == 0 else 'Not available'}")
    if exit_code != 0:
        logger.error(f"Docker check error: {stderr}")
    return exit_code == 0

async def check_docker_image_exists(distro: str, image: str) -> bool:
    """Check if Docker image exists in WSL"""
    logger.info(f"Checking if Docker image exists: {image}")
    stdout, stderr, exit_code = await run_wsl_command(distro, ["docker", "image", "inspect", image], timeout=5)
    return exit_code == 0

async def pull_docker_image(distro: str, image: str) -> bool:
    """Pull Docker image in WSL"""
    logger.info(f"Pulling Docker image: {image}")
    stdout, stderr, exit_code = await run_wsl_command(distro, ["docker", "pull", image], timeout=120)
    logger.info(f"Image pull result: {'Success' if exit_code == 0 else 'Failed'}")
    return exit_code == 0

async def cleanup_old_containers(distro: str) -> None:
    """Find and remove containers created by this script that might be dangling"""
    # Find containers with our label
    logger.info("Cleaning up old containers")
    stdout, stderr, exit_code = await run_wsl_command(
        distro,
        ["docker", "ps", "-a", "--filter", "label=created_by=python_mcp_server", "--format", "{{.ID}}"]
    )
    
    if exit_code != 0:
        logger.error(f"Error listing containers: {stderr}")
        return
    
    container_ids = stdout.strip().split("\n")
    for container_id in container_ids:
        if container_id:
            # Remove container
            logger.info(f"Removing old container {container_id}")
            await run_wsl_command(distro, ["docker", "rm", "-f", container_id])

def windows_to_wsl_path(distro: str, windows_path: str) -> str:
    """
    Convert a Windows path to a WSL path using synchronous subprocess.
    This is a helper function for paths and can be run synchronously.
    """
    try:
        distro_arg = ["-d", distro] if distro else []
        cmd = ["wsl"] + distro_arg + ["wslpath", windows_path]
        
        logger.debug(f"Converting path with command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        wsl_path = result.stdout.strip()
        logger.debug(f"Converted {windows_path} to {wsl_path}")
        return wsl_path
    except subprocess.SubprocessError as e:
        logger.error(f"Error converting Windows path to WSL path: {e}")
        
        # Fallback: attempt to convert path manually
        if ":" in windows_path:
            drive, path = windows_path.split(":", 1)
            path = path.replace('\\\\', '/').replace('\\', '/')
            wsl_path = f"/mnt/{drive.lower()}{path}"
            logger.info(f"Fallback path conversion: {windows_path} -> {wsl_path}")
            return wsl_path
        return windows_path

def save_execution_result(state: AppState, execution_id: str, info: Dict[str, Any]) -> None:
    """Save execution result to state and file"""
    # Update in-memory state
    state.execution_results[execution_id] = info
    
    try:
        # Also save to file for persistence
        with open(EXECUTION_MAPPING_FILE, 'w') as f:
            json.dump(state.execution_results, f, indent=2)
        
        logger.info(f"Saved execution result: {execution_id}")
    except Exception as e:
        logger.error(f"Error saving execution result: {e}")

@mcp.tool()
async def check_status(ctx: Context) -> str:
    """Check if the Python MCP server is working properly"""
    try:
        logger.info("check_status tool called")
        state = ctx.request_context.lifespan_context
        
        # Get WSL status
        wsl_status = "Available" if state.wsl_distro else "Not available"
        wsl_distro = state.wsl_distro if state.wsl_distro else "None"
        
        # Get Docker status
        docker_status = "Available" if state.docker_available else "Not available"
        docker_image_status = "Available" if state.docker_image_available else "Not available"
        
        status_text = [
            "Python Docker MCP Server Status:",
            f"WSL Status: {wsl_status}",
            f"WSL Distribution: {wsl_distro}",
            f"Docker Status: {docker_status}",
            f"Docker Image Status: {docker_image_status}",
            f"Docker Image: {DOCKER_IMAGE}",
            f"Python Files Directory: {PYTHON_FILES_DIR}",
            f"Output Directory: {OUTPUT_DIR}",
            f"Python Version: {sys.version}"
        ]
        
        return "\n".join(status_text)
    except Exception as e:
        logger.exception("Error in check_status tool")
        return f"Error checking status: {str(e)}"

@mcp.tool()
async def execute_python_file(
    ctx: Context,
    filename: str,
    args: List[str] = None,
    env_vars: Dict[str, str] = None,
    timeout: int = CONTAINER_TIMEOUT
) -> str:
    """Execute a Python file with optional arguments and environment variables in a Docker container
    
    Args:
        filename: Name of the Python file to execute (with or without .py extension)
        args: Optional list of command-line arguments to pass to the script
        env_vars: Optional dictionary of environment variables to set
        timeout: Maximum execution time in seconds (default: 30)
    """
    try:
        state = ctx.request_context.lifespan_context
        logger.info(f"execute_python_file called with filename: {filename}")
        
        # Default values
        if args is None:
            args = []
        if env_vars is None:
            env_vars = {}
        
        # Check if WSL and Docker are available
        if not state.wsl_distro:
            return "Error: WSL is not available. Please check your WSL installation."
        
        if not state.docker_available:
            return "Error: Docker is not available in WSL. Please check your Docker installation."
        
        # Ensure filename has .py extension
        if not filename.endswith('.py'):
            filename = f"{filename}.py"
        
        # Full path for the Python file
        file_path = PYTHON_FILES_DIR / filename
        
        if not file_path.exists():
            return f"Error: Python file '{filename}' not found"
        
        # Generate execution ID and timestamp
        execution_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Convert Windows path to WSL path for Docker volume mounting
        wsl_file_dir = windows_to_wsl_path(state.wsl_distro, str(PYTHON_FILES_DIR))
        
        logger.info(f"Executing in WSL Docker container: {filename}")
        logger.info(f"WSL dir path: {wsl_file_dir}")
        
        # Check Docker image availability
        if not state.docker_image_available:
            # Try to pull it one more time
            if not await pull_docker_image(state.wsl_distro, DOCKER_IMAGE):
                return f"Error: Docker image {DOCKER_IMAGE} not available and could not be pulled"
        
        # Build the Docker command
        container_name = f"python_mcp_{execution_id}"
        docker_cmd = [
            "docker", "run",
            "--name", container_name,
            "--rm",  # Remove container when done
            "-v", f"{wsl_file_dir}:{CONTAINER_WORK_DIR}:ro",  # Mount as read-only
            "--memory", CONTAINER_MEMORY_LIMIT,
            "--cpus", CONTAINER_CPU_LIMIT,
            "--network", "none",  # No network access
            "-w", CONTAINER_WORK_DIR,
            "--label", "created_by=python_mcp_server",
            "--label", f"execution_id={execution_id}"
        ]
        
        # Add env vars if provided
        for key, value in env_vars.items():
            docker_cmd.extend(["-e", f"{key}={value}"])
        
        # Add the image and command
        docker_cmd.append(DOCKER_IMAGE)
        
        # Add the Python command with args
        docker_cmd.extend(["python", f"{CONTAINER_WORK_DIR}/{filename}"])
        
        # Add args if provided
        if args:
            docker_cmd.extend(args)
        
        logger.info(f"Docker command: {' '.join(docker_cmd)}")
        
        # Progress reporting
        await ctx.report_progress(0, 1)
        
        # Execute Docker command in WSL
        stdout, stderr, exit_code = await run_wsl_command(state.wsl_distro, docker_cmd, timeout=timeout)
        
        # Progress update
        await ctx.report_progress(1, 1)
        
        # Prepare output file path for storing results
        output_file = OUTPUT_DIR / f"execution_{timestamp}_{execution_id}.txt"
        
        # Save execution info
        execution_info = {
            "filename": filename,
            "timestamp": timestamp,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "args": args,
            "env_vars": env_vars,
            "output_file": str(output_file),
            "docker_container": True,
            "docker_image": DOCKER_IMAGE
        }
        
        save_execution_result(state, execution_id, execution_info)
        
        # Write output to file
        with open(output_file, 'w') as f:
            f.write(f"=== WSL Docker Execution of {filename} ===\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Docker Image: {DOCKER_IMAGE}\n")
            f.write(f"Command: {' '.join(docker_cmd)}\n")
            f.write(f"Exit code: {exit_code}\n\n")
            f.write("=== STDOUT ===\n")
            f.write(stdout)
            f.write("\n\n=== STDERR ===\n")
            f.write(stderr)
        
        # Determine status based on exit code
        if exit_code == 0:
            status = "Success"
        elif exit_code == -1 and "timed out" in stderr:
            status = f"Error: Execution timed out after {timeout} seconds"
        else:
            status = f"Error (exit code: {exit_code})"
        
        # Format the output
        result_text = [
            f"Execution ID: {execution_id}",
            f"Status: {status}",
            f"Python file: {filename}",
            f"Docker Image: {DOCKER_IMAGE}",
            f"Arguments: {' '.join(args) if args else 'None'}",
            f"",
            f"=== STDOUT ===",
            stdout or "(No output)",
            f"",
            f"=== STDERR ===",
            stderr or "(No errors)"
        ]
        
        return "\n".join(result_text)
    
    except Exception as e:
        logger.exception("Error in execute_python_file")
        return f"Error executing Python file: {str(e)}"

@mcp.tool()
async def get_execution_results(ctx: Context, execution_id: str) -> str:
    """Get detailed results of a previous execution by ID
    
    Args:
        execution_id: The unique ID of the execution
    """
    try:
        state = ctx.request_context.lifespan_context
        logger.info(f"get_execution_results called with execution_id: {execution_id}")
        
        # Get execution info
        execution_info = state.execution_results.get(execution_id)
        
        if not execution_info:
            return f"Error: No execution found with ID {execution_id}"
        
        # Format the results
        result = [
            f"Execution ID: {execution_id}",
            f"Python file: {execution_info['filename']}",
            f"Timestamp: {execution_info['timestamp']}"
        ]
        
        # Add Docker-specific info if it exists
        if execution_info.get('docker_container', False):
            result.append(f"Docker Image: {execution_info.get('docker_image', 'unknown')}")
        
        result.extend([
            f"Exit code: {execution_info['exit_code']}",
            f"Arguments: {' '.join(execution_info['args']) if execution_info['args'] else 'None'}",
            f"",
            f"=== STDOUT ===",
            execution_info['stdout'] or "(No output)",
            f"",
            f"=== STDERR ===",
            execution_info['stderr'] or "(No errors)"
        ])
        
        return "\n".join(result)
    
    except Exception as e:
        logger.exception("Error in get_execution_results")
        return f"Error getting execution results: {str(e)}"

if __name__ == "__main__":
    # Log basic info
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    # Check if run with --web flag for SSE mode
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        # Web mode (SSE) - for web clients
        import uvicorn
        from starlette.applications import Starlette
        from starlette.middleware.cors import CORSMiddleware
        from starlette.routing import Mount
        
        # Create Starlette application with the MCP SSE app mounted at the root
        app = Starlette(
            routes=[
                Mount('/', app=mcp.sse_app()),
            ]
        )
        
        # Add CORS middleware to allow cross-origin requests
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # For development; restrict in production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Get port from arguments or environment or default
        port = int(os.environ.get("MCP_PORT", 8001))
        if len(sys.argv) > 2:
            try:
                port = int(sys.argv[2])
            except ValueError:
                pass
                
        print(f"Starting Web MCP server on port {port}")
        uvicorn.run(app, host="127.0.0.1", port=port)
    else:
        # STDIO mode - for Claude Desktop
        logger.info("Starting STDIO MCP server")
        mcp.run(transport='stdio')