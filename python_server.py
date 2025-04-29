"""
Python Execution MCP Server

This MCP server allows an LLM to execute Python files locally.
It provides tools for:
1. Executing Python files with support for arguments and environment variables
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
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Union, Tuple

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

# Create an MCP server
mcp = FastMCP(
    "python-execution-server",
    # Configure custom message path for web mode
    message_path="/mcp/messages/",
    sse_path="/mcp/sse"
)

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

@mcp.tool()
def execute_python_file(
    filename: str,
    args: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    ctx: Context = None
) -> str:
    """
    Execute a Python file with optional arguments and environment variables.
    
    Args:
        filename: Name of the Python file to execute (with or without .py extension)
        args: Optional list of command-line arguments to pass to the script
        env_vars: Optional dictionary of environment variables to set
        timeout: Maximum execution time in seconds (default: 30)
        
    Returns:
        Execution results including stdout, stderr, and execution ID
    """
    try:
        # Ensure filename has .py extension
        if not filename.endswith('.py'):
            filename = f"{filename}.py"
        
        # Full path for the Python file
        file_path = PYTHON_FILES_DIR / filename
        
        if not file_path.exists():
            return f"Error: Python file '{filename}' not found"
        
        # Create environment for subprocess
        process_env = os.environ.copy()
        if env_vars:
            process_env.update(env_vars)
        
        # Prepare command
        cmd = [sys.executable, str(file_path)]
        if args:
            cmd.extend(args)
        
        if ctx:
            ctx.info(f"Executing: {' '.join(cmd)}")
        
        # Create output file path for storing results
        execution_id = generate_unique_id()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = OUTPUT_DIR / f"execution_{timestamp}_{execution_id}.txt"
        
        # Execute the command
        result = subprocess.run(
            cmd,
            env=process_env,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        # Capture results
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode
        
        # Save execution info
        execution_info = {
            "filename": filename,
            "timestamp": timestamp,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "args": args or [],
            "env_vars": env_vars or {},
            "output_file": str(output_file)
        }
        
        save_execution_result(execution_id, execution_info)
        
        # Write output to file
        with open(output_file, 'w') as f:
            f.write(f"=== Execution of {filename} ===\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"Exit code: {exit_code}\n\n")
            f.write("=== STDOUT ===\n")
            f.write(stdout)
            f.write("\n\n=== STDERR ===\n")
            f.write(stderr)
        
        # Prepare response
        if exit_code == 0:
            status = "Success"
        else:
            status = f"Error (exit code: {exit_code})"
        
        # Format the output
        result_text = [
            f"Execution ID: {execution_id}",
            f"Status: {status}",
            f"Python file: {filename}",
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
    
    except subprocess.TimeoutExpired:
        error_message = f"Error: Execution timed out after {timeout} seconds"
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
            f"Timestamp: {execution_info['timestamp']}",
            f"Exit code: {execution_info['exit_code']}",
            f"Arguments: {' '.join(execution_info['args']) if execution_info['args'] else 'None'}",
            f"",
            f"=== STDOUT ===",
            execution_info['stdout'] or "(No output)",
            f"",
            f"=== STDERR ===",
            execution_info['stderr'] or "(No errors)"
        ]
        
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

# Test endpoint to verify routing
async def test_endpoint(request):
    return JSONResponse({
        "status": "Python Execution Server is working", 
        "python_files_dir": str(PYTHON_FILES_DIR),
        "output_dir": str(OUTPUT_DIR),
        "endpoints": {
            "mcp_sse": "/mcp/sse",
            "mcp_messages": "/mcp/messages/",
            "execution_output": "/python/output/{execution_id}",
            "test": "/python/test"
        }
    })

# Function to create a Starlette application for web mode
def create_app():
    # Define routes
    routes = [
        Route('/python/test', endpoint=test_endpoint, methods=["GET"]),
        Route('/python/output/{execution_id:str}', endpoint=get_execution_output, methods=["GET"]),
    ]
    
    # Mount MCP app
    mcp_app = mcp.sse_app()
    routes.append(Mount('/mcp', app=mcp_app))
    
    app = Starlette(routes=routes)
    return app

if __name__ == "__main__":
    # Ensure directories exist
    PYTHON_FILES_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Initialize execution mapping file if it doesn't exist
    if not EXECUTION_MAPPING_FILE.exists():
        with open(EXECUTION_MAPPING_FILE, 'w') as f:
            json.dump({}, f)
    
    print(f"Python files directory: {PYTHON_FILES_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    
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
        uvicorn.run(app, host="0.0.0.0", port=port)
        
    else:
        # STDIO mode - for Claude Desktop
        print(f"Starting STDIO MCP server for Python execution")
        mcp.run(transport='stdio')