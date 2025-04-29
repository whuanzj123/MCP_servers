"""
Python Execution MCP Server with Docker Integration

This MCP server allows an LLM to execute Python files within Docker containers in WSL2.
It provides tools for:
1. Executing Python files in isolated containers
2. Creating Python files with provided code
3. Listing available Python files
4. Reading Python file contents
"""

import os
import sys
import uuid
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Union, Tuple
import docker
from docker.errors import DockerException
from mcp.server.fastmcp import FastMCP, Context
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse, Response, PlainTextResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure the working directory for Python files
ROOT_DIR = Path(__file__).parent.absolute()
PYTHON_FILES_DIR = ROOT_DIR / "python_files"
PYTHON_FILES_DIR.mkdir(exist_ok=True)

# Configure the output directory for execution results
OUTPUT_DIR = ROOT_DIR / "python_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# Storage for mapping execution IDs to results
EXECUTION_MAPPING_FILE = OUTPUT_DIR / "execution_mappings.json"

# Docker configuration
DOCKER_IMAGE = "python:3.11-slim"  # Base Python image to use
CONTAINER_WORK_DIR = "/app"  # Working directory inside container
CONTAINER_TIMEOUT = 30  # Default timeout in seconds
CONTAINER_MEMORY_LIMIT = "512m"  # Memory limit per container
CONTAINER_CPU_LIMIT = 1.0  # CPU limit (1 core)

# Create an MCP server
mcp = FastMCP(
    "python-execution-server",
    # Configure custom message path for web mode
    message_path="/mcp/messages/",
    sse_path="/mcp/sse"
)

# Initialize Docker client
docker_client = None
try:
    docker_client = docker.from_env()
    # Test Docker connection
    docker_client.ping()
    logger.info("Successfully connected to Docker")
except DockerException as e:
    logger.error(f"Failed to connect to Docker: {e}")
    logger.error("Make sure Docker is running in WSL2 and you have proper permissions")

def windows_to_wsl_path(windows_path: str) -> str:
    """
    Convert a Windows path to a WSL path.
    Example: C:\\Users\\username\\file.py -> /mnt/c/Users/username/file.py
    """
    try:
        # Run wslpath command to convert Windows path to WSL path
        result = subprocess.run(
            ["wsl", "wslpath", windows_path],
            capture_output=True,
            text=True,
            check=True
        )
        wsl_path = result.stdout.strip()
        return wsl_path
    except subprocess.SubprocessError as e:
        logger.error(f"Error converting Windows path to WSL path: {e}")
        # Fallback: attempt to convert path manually
        if ":" in windows_path:
            drive, path = windows_path.split(":", 1)
            path = path.replace('\\\\', '/').replace('\\', '/')
            return f"/mnt/{drive.lower()}{path}"
        return windows_path

def save_execution_result(execution_id: str, info: Dict[str, Any]):
    """Save the mapping between execution ID and results"""
    mappings = {}
    if EXECUTION_MAPPING_FILE.exists():
        with open(EXECUTION_MAPPING_FILE, 'r') as f:
            try:
                mappings = json.load(f)
            except json.JSONDecodeError:
                mappings = {}
    
    mappings[execution_id] = info
    
    with open(EXECUTION_MAPPING_FILE, 'w') as f:
        json.dump(mappings, f, indent=2)
    
    logger.info(f"Saved execution result: {execution_id}")

def get_execution_result(execution_id: str) -> Optional[Dict[str, Any]]:
    """Get the execution result by ID"""
    if not EXECUTION_MAPPING_FILE.exists():
        return None
    
    with open(EXECUTION_MAPPING_FILE, 'r') as f:
        try:
            mappings = json.load(f)
            return mappings.get(execution_id)
        except json.JSONDecodeError:
            return None

def generate_unique_id() -> str:
    """Generate a unique ID for execution tracking"""
    return str(uuid.uuid4())

def cleanup_old_containers():
    """Find and remove containers created by this script that might be dangling"""
    try:
        if docker_client:
            containers = docker_client.containers.list(
                all=True,
                filters={"label": "created_by=python_mcp_server"}
            )
            
            for container in containers:
                try:
                    # Check if container is still running and older than timeout
                    if container.status == "running":
                        created_at = container.attrs['Created']
                        # Simple check if container is running for more than 2x the timeout
                        # This is a safety measure for stuck containers
                        container_age = time.time() - created_at
                        if container_age > (CONTAINER_TIMEOUT * 2):
                            logger.warning(f"Killing old container {container.id}")
                            container.kill()
                    
                    # Remove container
                    logger.info(f"Removing old container {container.id}")
                    container.remove(force=True)
                except docker.errors.APIError as e:
                    logger.error(f"Error cleaning up container {container.id}: {e}")
    except Exception as e:
        logger.error(f"Error during container cleanup: {e}")

@mcp.tool()
def execute_python_file(
    filename: str,
    args: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, str]] = None,
    timeout: int = CONTAINER_TIMEOUT,
    ctx: Context = None
) -> str:
    """
    Execute a Python file within a Docker container with optional arguments and environment variables.
    
    Args:
        filename: Name of the Python file to execute (with or without .py extension)
        args: Optional list of command-line arguments to pass to the script
        env_vars: Optional dictionary of environment variables to set
        timeout: Maximum execution time in seconds (default: 30)
        
    Returns:
        Execution results including stdout, stderr, and execution ID
    """
    if not docker_client:
        return "Error: Docker connection is not available. Make sure Docker is running in WSL2."
    
    try:
        # Clean up any old containers
        cleanup_old_containers()
        
        # Ensure filename has .py extension
        if not filename.endswith('.py'):
            filename = f"{filename}.py"
        
        # Full path for the Python file
        file_path = PYTHON_FILES_DIR / filename
        
        if not file_path.exists():
            return f"Error: Python file '{filename}' not found"
        
        # Generate execution ID
        execution_id = generate_unique_id()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Convert Windows path to WSL path for Docker volume mounting
        wsl_file_path = windows_to_wsl_path(str(file_path))
        wsl_dir_path = windows_to_wsl_path(str(PYTHON_FILES_DIR))
        
        if ctx:
            ctx.info(f"Executing in Docker container: {filename}")
            ctx.info(f"WSL path: {wsl_file_path}")
        
        # Prepare environment variables
        container_env = env_vars.copy() if env_vars else {}
        
        # Prepare command args
        cmd = ["python", f"{CONTAINER_WORK_DIR}/{filename}"]
        if args:
            cmd.extend(args)
            
        if ctx:
            ctx.info(f"Command: {' '.join(cmd)}")
        
        # Create and run container
        try:
            container = docker_client.containers.run(
                image=DOCKER_IMAGE,
                command=cmd,
                volumes={wsl_dir_path: {"bind": CONTAINER_WORK_DIR, "mode": "ro"}},
                environment=container_env,
                working_dir=CONTAINER_WORK_DIR,
                detach=True,
                remove=False,  # We'll remove it after getting logs
                mem_limit=CONTAINER_MEMORY_LIMIT,
                cpu_quota=int(CONTAINER_CPU_LIMIT * 100000),  # Docker uses microseconds
                network_mode="none",  # Restrict network access for security
                labels={"created_by": "python_mcp_server", "execution_id": execution_id}
            )
            
            # Wait for container to finish or timeout
            try:
                exit_code = container.wait(timeout=timeout)["StatusCode"]
                finished = True
            except docker.errors.APIError:
                # Container likely timed out
                container.kill()
                exit_code = -1
                finished = False
            
            # Get logs (stdout/stderr)
            stdout = container.logs(stdout=True, stderr=False).decode('utf-8')
            stderr = container.logs(stdout=False, stderr=True).decode('utf-8')
            
            # Clean up container
            try:
                container.remove(force=True)
            except docker.errors.APIError as e:
                logger.error(f"Error removing container: {e}")
            
            # Prepare output file path for storing results
            output_file = OUTPUT_DIR / f"execution_{timestamp}_{execution_id}.txt"
            
            # Save execution info
            execution_info = {
                "filename": filename,
                "timestamp": timestamp,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "args": args or [],
                "env_vars": env_vars or {},
                "output_file": str(output_file),
                "docker_container": True,
                "docker_image": DOCKER_IMAGE,
                "finished": finished
            }
            
            save_execution_result(execution_id, execution_info)
            
            # Write output to file
            with open(output_file, 'w') as f:
                f.write(f"=== Docker Execution of {filename} ===\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"Docker Image: {DOCKER_IMAGE}\n")
                f.write(f"Command: {' '.join(cmd)}\n")
                f.write(f"Exit code: {exit_code}\n\n")
                f.write("=== STDOUT ===\n")
                f.write(stdout)
                f.write("\n\n=== STDERR ===\n")
                f.write(stderr)
            
            # Format status based on exit code
            if finished and exit_code == 0:
                status = "Success"
            elif not finished:
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
            
            if ctx:
                ctx.info(f"Execution completed with exit code {exit_code}")
            
            return "\n".join(result_text)
            
        except docker.errors.ImageNotFound:
            error_message = f"Error: Docker image '{DOCKER_IMAGE}' not found. Pulling..."
            try:
                if ctx:
                    ctx.info(f"Pulling Docker image {DOCKER_IMAGE}...")
                docker_client.images.pull(DOCKER_IMAGE)
                # Retry after pulling
                return execute_python_file(filename, args, env_vars, timeout, ctx)
            except Exception as e:
                return f"{error_message} Failed to pull image: {str(e)}"
                
        except docker.errors.APIError as e:
            error_message = f"Docker API error: {str(e)}"
            if ctx:
                ctx.error(error_message)
            return error_message
    
    except Exception as e:
        error_message = f"Error executing Python file: {str(e)}"
        if ctx:
            ctx.error(error_message)
        return error_message

@mcp.tool()
def get_execution_results(
    execution_id: str,
    ctx: Context = None
) -> str:
    """
    Get detailed results of a previous execution by ID.
    
    Args:
        execution_id: The unique ID of the execution
        
    Returns:
        Detailed execution results
    """
    try:
        # Get execution info
        execution_info = get_execution_result(execution_id)
        
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
        error_message = f"Error getting execution results: {str(e)}"
        if ctx:
            ctx.error(error_message)
        return error_message

# Function to get execution output directly (for web interface)
async def get_execution_output(request):
    execution_id = request.path_params.get("execution_id")
    
    if not execution_id:
        return JSONResponse({"error": "No execution ID provided"}, status_code=400)
    
    execution_info = get_execution_result(execution_id)
    if not execution_info:
        return JSONResponse({"error": f"No execution found with ID {execution_id}"}, status_code=404)
    
    # Return the output as plain text
    content = f"=== STDOUT ===\n{execution_info['stdout']}\n\n=== STDERR ===\n{execution_info['stderr']}"
    return PlainTextResponse(content)

# Function to check Docker status (for web interface)
async def check_docker_status(request):
    status = {
        "docker_available": docker_client is not None,
        "docker_running": False,
        "docker_version": None,
        "python_image_available": False,
        "error": None
    }
    
    try:
        if docker_client:
            # Check if Docker daemon is running
            version_info = docker_client.version()
            status["docker_running"] = True
            status["docker_version"] = version_info.get("Version")
            
            # Check if Python image is available
            try:
                docker_client.images.get(DOCKER_IMAGE)
                status["python_image_available"] = True
            except docker.errors.ImageNotFound:
                status["python_image_available"] = False
                status["error"] = f"Python image '{DOCKER_IMAGE}' not found. Will be pulled on first execution."
    except Exception as e:
        status["error"] = str(e)
    
    return JSONResponse(status)

# Test endpoint to verify routing
async def test_endpoint(request):
    return JSONResponse({
        "status": "Python Execution Server with Docker is working", 
        "python_files_dir": str(PYTHON_FILES_DIR),
        "output_dir": str(OUTPUT_DIR),
        "docker_image": DOCKER_IMAGE,
        "endpoints": {
            "mcp_sse": "/mcp/sse",
            "mcp_messages": "/mcp/messages/",
            "execution_output": "/python/output/{execution_id}",
            "docker_status": "/python/docker_status",
            "test": "/python/test"
        }
    })

# Function to create a Starlette application for web mode
def create_app():
    # Define routes
    routes = [
        Route('/python/test', endpoint=test_endpoint, methods=["GET"]),
        Route('/python/output/{execution_id:str}', endpoint=get_execution_output, methods=["GET"]),
        Route('/python/docker_status', endpoint=check_docker_status, methods=["GET"]),
    ]
    
    # Mount MCP app
    mcp_app = mcp.sse_app()
    routes.append(Mount('/mcp', app=mcp_app))
    
    app = Starlette(routes=routes)
    return app

if __name__ == "__main__":
    # Check Docker connectivity
    if not docker_client:
        print("WARNING: Docker is not available. Please make sure Docker is running in WSL2.")
        print("The server will start, but container execution will not work.")
    
    # Ensure directories exist
    PYTHON_FILES_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Initialize execution mapping file if it doesn't exist
    if not EXECUTION_MAPPING_FILE.exists():
        with open(EXECUTION_MAPPING_FILE, 'w') as f:
            json.dump({}, f)
    
    print(f"Python files directory: {PYTHON_FILES_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Docker image: {DOCKER_IMAGE}")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        # Web mode (SSE)
        import uvicorn
        
        port = 8000
        if len(sys.argv) > 2:
            try:
                port = int(sys.argv[2])
            except ValueError:
                pass
        
        # Set environment variable for server URL if not already set
        if not os.environ.get('MCP_SERVER_URL'):
            os.environ['MCP_SERVER_URL'] = f'http://localhost:{port}'
            
        app = create_app()
        print(f"Starting Web MCP server on port {port}")
        print(f"MCP SSE endpoint: /mcp/sse")
        print(f"MCP messages endpoint: /mcp/messages/")
        print(f"Execution output endpoint: /python/output/{{execution_id}}")
        print(f"Docker status endpoint: /python/docker_status")
        uvicorn.run(app, host="0.0.0.0", port=port)
        
    else:
        # STDIO mode - for Claude Desktop
        print(f"Starting STDIO MCP server for Python execution with Docker")
        mcp.run(transport='stdio')
