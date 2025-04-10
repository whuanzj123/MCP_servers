from mcp.server.fastmcp import FastMCP
import subprocess
import os
import re
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
import sys

# Set the fixed Git repository path - locked to your specified repo
GIT_REPO_PATH = r"C:/Users/Administrator/Desktop/TestField"

# Create an MCP server
mcp = FastMCP("GitTools")

def run_git_command(command, args=None, subpath=None):
    """Run a git command with specified arguments in a specific subfolder.
    
    Args:
        command: The git command to run
        args: Command arguments
        subpath: Optional subfolder path relative to the main repository
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
def git_version() -> str:
    """Get the installed Git version."""
    return run_git_command("version")

@mcp.tool()
def git_status(subpath: str = None) -> str:
    """Show the working tree status.
    
    Args:
        subpath: Optional subfolder path relative to repository root
    """
    return run_git_command("status", subpath=subpath)

@mcp.tool()
def git_log(n: int = 10, subpath: str = None) -> str:
    """Show commit logs.
    
    Args:
        n: Number of commits to show (default: 10)
        subpath: Optional subfolder path relative to repository root
    """
    return run_git_command("log", [f"-n{n}", "--oneline"], subpath=subpath)

@mcp.tool()
def git_add(files: str, subpath: str = None) -> str:
    """Add file contents to the index.
    
    Args:
        files: File pattern to add (e.g., ".", "*.py", "file.txt")
        subpath: Optional subfolder path relative to repository root
    """
    # Basic sanitization to prevent command injection
    if re.search(r'[;&|]', files):
        return "Error: Invalid file pattern"
    return run_git_command("add", files, subpath=subpath)

@mcp.tool()
def git_commit(message: str, subpath: str = None) -> str:
    """Record changes to the repository.
    
    Args:
        message: Commit message
        subpath: Optional subfolder path relative to repository root
    """
    # Simple sanitization
    message = message.replace('"', '\\"')
    return run_git_command("commit", ["-m", message], subpath=subpath)

@mcp.tool()
def git_branch(subpath: str = None) -> str:
    """List, create, or delete branches.
    
    Args:
        subpath: Optional subfolder path relative to repository root
    """
    return run_git_command("branch", subpath=subpath)

@mcp.tool()
def git_checkout(branch_or_file: str, subpath: str = None) -> str:
    """Switch branches or restore working tree files.
    
    Args:
        branch_or_file: The branch to checkout or file to restore
        subpath: Optional subfolder path relative to repository root
    """
    # Basic sanitization to prevent command injection
    if re.search(r'[;&|]', branch_or_file):
        return "Error: Invalid branch or file name"
    return run_git_command("checkout", branch_or_file, subpath=subpath)

@mcp.tool()
def git_ls_files(subpath: str = None) -> str:
    """Show information about files in the index and the working tree.
    
    Args:
        subpath: Optional subfolder path relative to repository root
    """
    return run_git_command("ls-files", subpath=subpath)

@mcp.tool()
def git_diff(files: str = None, subpath: str = None) -> str:
    """Show changes between commits, commit and working tree, etc.
    
    Args:
        files: Optional specific files to diff
        subpath: Optional subfolder path relative to repository root
    """
    return run_git_command("diff", files, subpath=subpath)

@mcp.tool()
def git_execute(command: str, subpath: str = None) -> str:
    """Execute a git command directly with arguments.
    
    Args:
        command: Git command and arguments (e.g., "log -n5", "status -s")
        subpath: Optional subfolder path relative to repository root
    """
    # Sanitization for the general command
    if re.search(r'[;&|`$]', command) or '..' in command:
        return "Error: Potentially unsafe command detected"
    
    parts = command.split()
    if not parts:
        return "Error: Empty command"
    
    git_cmd = parts[0]
    args = parts[1:] if len(parts) > 1 else []
    
    # Whitelist of allowed git commands
    allowed_commands = [
        'version', 'status', 'log', 'add', 'commit', 'branch', 
        'checkout', 'init', 'diff', 'show', 'remote', 'fetch', 
        'config', 'tag', 'ls-files'
    ]
    
    if git_cmd not in allowed_commands:
        return f"Error: Command '{git_cmd}' is not allowed"
    
    return run_git_command(git_cmd, args, subpath=subpath)

@mcp.resource("git://subfolders")
def list_subfolders() -> str:
    """List all subfolders in the Git repository."""
    try:
        result = []
        for root, dirs, files in os.walk(GIT_REPO_PATH):
            # Get relative path from the repository root
            rel_path = os.path.relpath(root, GIT_REPO_PATH)
            if rel_path != '.':  # Skip the repository root
                result.append(rel_path)
        
        return '\n'.join(result) if result else "No subfolders found."
    except Exception as e:
        return f"Error listing subfolders: {str(e)}"

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