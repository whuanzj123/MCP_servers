from mcp.server.fastmcp import FastMCP
import os
import sys
import tempfile
import subprocess
import json
import time
import uuid
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

# Create an MCP server
mcp = FastMCP("Python Executor")

# Configure execution environment
EXECUTION_DIR = os.path.join(tempfile.gettempdir(), "python_executor")
DOCKER_IMAGE = "python:3.11-slim"  # Base Python image
MAX_EXECUTION_TIME = 30  # Maximum execution time in seconds
MEMORY_LIMIT = "512m"  # Memory limit for container

# Ensure execution directory exists
os.makedirs(EXECUTION_DIR, exist_ok=True)

def sanitize_filename(filename):
    """Create a safe filename from user input"""
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
    return ''.join(c for c in filename if c in safe_chars)

def create_unique_execution_id():
    """Create a unique ID for this execution"""
    return str(uuid.uuid4())

@mcp.tool()
def write_python_file(code: str, filename: str = "script.py") -> str:
    """Write Python code to a file.
    
    Args:
        code: The Python code to write
        filename: Optional filename (default: script.py)
    
    Returns:
        The path to the created file
    """
    try:
        # Sanitize filename
        safe_filename = sanitize_filename(filename)
        if not safe_filename.endswith('.py'):
            safe_filename += '.py'
            
        # Create a unique directory for this execution
        execution_id = create_unique_execution_id()
        execution_dir = os.path.join(EXECUTION_DIR, execution_id)
        os.makedirs(execution_dir, exist_ok=True)
        
        # Write the code to the file
        file_path = os.path.join(execution_dir, safe_filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)
        
        return json.dumps({
            "execution_id": execution_id,
            "file_path": file_path,
            "filename": safe_filename,
            "message": f"Python code written to {safe_filename} successfully"
        })
        
    except Exception as e:
        return json.dumps({
            "error": f"Failed to write Python file: {str(e)}"
        })

@mcp.tool()
def execute_python_code(execution_id: str, filename: str = "script.py", 
                        args: str = "", requirements: str = "") -> str:
    """Execute Python code in a secure Docker container.
    
    Args:
        execution_id: The execution ID returned from write_python_file
        filename: The Python file to execute
        args: Optional command-line arguments for the script
        requirements: Optional pip packages to install (comma-separated)
    
    Returns:
        The execution results
    """
    try:
        # Validate execution_id
        execution_dir = os.path.join(EXECUTION_DIR, execution_id)
        if not os.path.exists(execution_dir):
            return json.dumps({
                "error": f"Invalid execution ID: {execution_id}"
            })
        
        # Validate filename
        safe_filename = sanitize_filename(filename)
        file_path = os.path.join(execution_dir, safe_filename)
        if not os.path.exists(file_path):
            return json.dumps({
                "error": f"File not found: {safe_filename}"
            })
        
        # Parse requirements
        req_list = []
        if requirements:
            req_list = [pkg.strip() for pkg in requirements.split(",")]
        
        # Create requirements.txt if needed
        if req_list:
            req_path = os.path.join(execution_dir, "requirements.txt")
            with open(req_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(req_list))
        
        # Build Docker command
        docker_cmd = [
            "wsl", "docker", "run",
            "--rm",                          # Remove container after execution
            "--network=none",                # No network access
            f"--memory={MEMORY_LIMIT}",      # Memory limit
            "--cpus=0.5",                    # CPU limit
            f"--workdir=/app",               # Working directory
            f"--volume={execution_dir}:/app:ro",  # Mount code as read-only
            "--cap-drop=ALL",                # Drop all capabilities
            "--security-opt=no-new-privileges:true",  # No privilege escalation
            DOCKER_IMAGE
        ]
        
        # Add pip install if requirements exist
        full_cmd = docker_cmd.copy()
        if req_list:
            full_cmd.extend([
                "sh", "-c", 
                f"pip install --no-cache-dir -r requirements.txt && python {safe_filename} {args}"
            ])
        else:
            full_cmd.extend(["python", safe_filename])
            if args:
                full_cmd.extend(args.split())
        
        # Execute with timeout
        start_time = time.time()
        result = subprocess.run(
            full_cmd, 
            capture_output=True, 
            text=True, 
            timeout=MAX_EXECUTION_TIME
        )
        execution_time = time.time() - start_time
        
        # Return results
        return json.dumps({
            "execution_id": execution_id,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "execution_time": f"{execution_time:.2f} seconds",
            "success": result.returncode == 0
        }, indent=2)
        
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": f"Execution timed out after {MAX_EXECUTION_TIME} seconds",
            "execution_id": execution_id
        })
    except Exception as e:
        return json.dumps({
            "error": f"Failed to execute Python code: {str(e)}",
            "execution_id": execution_id
        })

@mcp.tool()
def clean_execution(execution_id: str) -> str:
    """Clean up execution files.
    
    Args:
        execution_id: The execution ID to clean up
    
    Returns:
        Status message
    """
    try:
        execution_dir = os.path.join(EXECUTION_DIR, execution_id)
        if not os.path.exists(execution_dir):
            return json.dumps({
                "message": f"Execution ID {execution_id} not found or already cleaned"
            })
        
        import shutil
        shutil.rmtree(execution_dir)
        
        return json.dumps({
            "message": f"Execution {execution_id} cleaned successfully"
        })
        
    except Exception as e:
        return json.dumps({
            "error": f"Failed to clean execution: {str(e)}"
        })

@mcp.tool()
def list_executions() -> str:
    """List all existing execution IDs.
    
    Returns:
        List of execution IDs and their files
    """
    try:
        executions = []
        for execution_id in os.listdir(EXECUTION_DIR):
            execution_path = os.path.join(EXECUTION_DIR, execution_id)
            if os.path.isdir(execution_path):
                files = os.listdir(execution_path)
                executions.append({
                    "execution_id": execution_id,
                    "files": files
                })
        
        return json.dumps({
            "executions": executions
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Failed to list executions: {str(e)}"
        })

@mcp.tool()
def check_docker() -> str:
    """Check if Docker is available and the required image exists.
    
    Returns:
        Docker status
    """
    try:
        # Check if Docker is installed and running
        docker_check = subprocess.run(
            ["wsl", "docker", "ps"], 
            capture_output=True, 
            text=True
        )
        
        if docker_check.returncode != 0:
            return json.dumps({
                "error": "Docker is not available or not running",
                "details": docker_check.stderr
            })
        
        # Check if our image exists
        image_check = subprocess.run(
            ["docker", "image", "inspect", DOCKER_IMAGE], 
            capture_output=True, 
            text=True
        )
        
        if image_check.returncode != 0:
            # Pull the image
            pull_result = subprocess.run(
                ["docker", "pull", DOCKER_IMAGE], 
                capture_output=True, 
                text=True
            )
            
            if pull_result.returncode != 0:
                return json.dumps({
                    "error": f"Failed to pull Docker image {DOCKER_IMAGE}",
                    "details": pull_result.stderr
                })
            
            return json.dumps({
                "status": "Docker is available",
                "image": f"{DOCKER_IMAGE} has been pulled successfully"
            })
        
        return json.dumps({
            "status": "Docker is available",
            "image": f"{DOCKER_IMAGE} is already available"
        })
        
    except Exception as e:
        return json.dumps({
            "error": f"Error checking Docker: {str(e)}"
        })

# Create Starlette application with the MCP SSE app mounted at the root
app = Starlette(
    routes=[
        Mount('/', app=mcp.sse_app()),
    ]
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    # Check if run with --web flag
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        # Web mode (SSE)
        import uvicorn
        
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
        print("Starting STDIO MCP server")
        mcp.run(transport='stdio')