from mcp.server.fastmcp import FastMCP
import subprocess
import os
import re
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
import sys
import shlex  # Import the shell lexical analyzer
# Set the fixed Git repository path - locked to your specified repo
GIT_REPO_PATH = r"C:/Users/Administrator/Desktop/TestField"

# Create an MCP server
mcp = FastMCP("GitTools")

def run_git_command(command, args=None, subpath=None):
    """Run a git command with specified arguments in a specific subfolder.
    
    Args:
        command: The git command to run
        args: Command arguments
        subpath: Optional subfolder path relative to repository root
    """
    # Start with the base git command
    cmd = ["git"]
    
    # Add the specific command
    cmd.append(command)
    
    # Add any arguments that were passed
    if args:
        if isinstance(args, list):
            cmd.extend(args)
        else:
            cmd.append(args)
    
    try:
        # Determine working directory
        working_dir = GIT_REPO_PATH
        
        if subpath:
            # Normalize the path to prevent directory traversal
            norm_path = os.path.normpath(subpath)
            
            # Prevent escaping the repository with path traversal
            if norm_path.startswith('..') or norm_path.startswith('/') or norm_path.startswith('\\'):
                return f"Error: Invalid path. Must be relative to repository root: {norm_path}"
                
            # Create full path by joining repository path with subfolder
            working_dir = os.path.join(GIT_REPO_PATH, norm_path)
            
            # Ensure the path exists
            if not os.path.exists(working_dir):
                return f"Error: Path does not exist: {norm_path}"
            
            # Final check to ensure we're still within the repository
            if not os.path.abspath(working_dir).startswith(os.path.abspath(GIT_REPO_PATH)):
                return f"Error: Path is outside the repository: {norm_path}"
        
        # Run the command in the specified directory
        result = subprocess.run(
            cmd, 
            cwd=working_dir, 
            text=True, 
            capture_output=True, 
            check=False  # Don't raise exception on non-zero exit
        )
        
        # Return both stdout and stderr
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"Error (code {result.returncode}): {result.stderr.strip()}"
    except Exception as e:
        return f"Failed to execute command: {str(e)}"

@mcp.tool()
def git_execute(command: str, subpath: str = None) -> str:
    """Execute a git command directly with arguments."""
    # Sanitization for the general command
    if re.search(r'[;&|`$]', command) or '..' in command:
        return "Error: Potentially unsafe command detected"
    
    try:
        # Use shlex.split to properly handle quoted arguments
        parts = shlex.split(command)
        if not parts:
            return "Error: Empty command"
        
        git_cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        
        # Whitelist of allowed git commands
        allowed_commands = [
            'version', 'status', 'log', 'add', 'commit', 'branch', 
            'checkout', 'init', 'diff', 'show', 'remote', 'fetch', 
            'config', 'tag', 'ls-files', 'pull', 'push'
        ]
        
        if git_cmd not in allowed_commands:
            return f"Error: Command '{git_cmd}' is not allowed"
        
        return run_git_command(git_cmd, args, subpath=subpath)
    except ValueError as e:
        return f"Error parsing command: {str(e)}"


# Create Starlette application with the MCP SSE app mounted at the root
app = Starlette(
    routes=[
        Mount('/', app=mcp.sse_app()),
    ]
)

# Add CORS middleware to allow cross-origin requests (important for Chainlit)
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
        # Web mode (SSE) - for Chainlit
        import uvicorn
        
        # Create Starlette application
        app = Starlette(
            routes=[
                Mount('/', app=mcp.sse_app()),
            ]
        )
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
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
        print("Starting STDIO MCP server")
        mcp.run(transport='stdio')