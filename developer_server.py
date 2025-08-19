from mcp.server.fastmcp import FastMCP
import os
import sys
import datetime
import json
import platform
import subprocess
import shutil
from pathlib import Path
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from typing import List, Optional, Dict, Any

# Determine base directory based on OS
system = platform.system()
if system == "Windows":
    BASE_DIR = os.path.expanduser("~/Desktop/TestField")
elif system == "Darwin":  # macOS
    BASE_DIR = os.path.expanduser("~/Desktop/TestField")
else:  # Linux or other
    BASE_DIR = os.path.expanduser("~/TestField")

# Create the base directory if it doesn't exist
os.makedirs(BASE_DIR, exist_ok=True)

# Create an MCP server
mcp = FastMCP("DeveloperTools")

def validate_path(path):
    """
    Validate a file path and check security constraints.
    
    This function:
    1. Normalizes the path
    2. Blocks access to any .env files
    3. Returns the full path
    """
    # Normalize the path
    full_path = os.path.normpath(os.path.join(BASE_DIR, path))
    
    # Check if the path is a .env file or has .env extension
    if (os.path.basename(full_path) == '.env' or 
        os.path.splitext(full_path)[1] == '.env' or
        os.path.basename(full_path).endswith('.env')):
        raise ValueError("Access denied: .env files are not accessible for security reasons")
    
    # Additional check for any path segment being .env
    path_parts = os.path.normpath(path).split(os.sep)
    if '.env' in path_parts:
        raise ValueError("Access denied: Paths containing .env directories are not accessible")
    
    return full_path

def run_git_command(args: List[str], subpath: str = None) -> Dict[str, Any]:
    """Run a git command and return structured result"""
    try:
        # Determine working directory
        working_dir = BASE_DIR
        
        if subpath:
            # Normalize the path to prevent directory traversal
            norm_path = os.path.normpath(subpath)
            
            # Prevent escaping the repository with path traversal
            if norm_path.startswith('..') or norm_path.startswith('/') or norm_path.startswith('\\'):
                return {"success": False, "error": f"Invalid path: {norm_path}"}
                
            # Create full path by joining repository path with subfolder
            working_dir = os.path.join(BASE_DIR, norm_path)
            
            # Ensure the path exists
            if not os.path.exists(working_dir):
                return {"success": False, "error": f"Path does not exist: {norm_path}"}
            
            # Final check to ensure we're still within the repository
            if not os.path.abspath(working_dir).startswith(os.path.abspath(BASE_DIR)):
                return {"success": False, "error": f"Path is outside the base directory: {norm_path}"}
        
        # Build the git command
        cmd = ["git"] + args
        
        # Run the command
        result = subprocess.run(
            cmd, 
            cwd=working_dir, 
            text=True, 
            capture_output=True, 
            check=False
        )
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to execute git command: {str(e)}"}

# ===== FILE SYSTEM OPERATIONS =====

@mcp.tool()
def copy_file(source_path: str, destination_path: str) -> str:
    """Copy a file from one location to another.
    
    Args:
        source_path: The source file path relative to the base directory
        destination_path: The destination path relative to the base directory
    """
    try:
        source_full_path = validate_path(source_path)
        destination_full_path = validate_path(destination_path)
        
        if not os.path.exists(source_full_path):
            return f"Error: Source file '{source_path}' does not exist"
        
        if not os.path.isfile(source_full_path):
            return f"Error: Source '{source_path}' is not a file"
            
        destination_dir = os.path.dirname(destination_full_path)
        os.makedirs(destination_dir, exist_ok=True)
        
        if os.path.exists(destination_full_path):
            return f"Error: Destination '{destination_path}' already exists"
        
        shutil.copy2(source_full_path, destination_full_path)
        return f"File copied successfully from '{source_path}' to '{destination_path}'"
        
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: Failed to copy file: {str(e)}"

@mcp.tool()
def list_files(directory: str = "") -> str:
    """List files and directories in the specified directory.
    
    Args:
        directory: The directory path relative to the base directory (default: root)
    """
    try:
        full_path = validate_path(directory)
        
        if not os.path.exists(full_path):
            return f"Error: Directory '{directory}' does not exist"
        
        if not os.path.isdir(full_path):
            return f"Error: '{directory}' is not a directory"
        
        items = os.listdir(full_path)
        result = []
        
        for item in items:
            item_path = os.path.join(full_path, item)
            item_type = "directory" if os.path.isdir(item_path) else "file"
            item_size = os.path.getsize(item_path) if os.path.isfile(item_path) else 0
            item_modified = datetime.datetime.fromtimestamp(
                os.path.getmtime(item_path)
            ).strftime("%Y-%m-%d %H:%M:%S")
            
            result.append({
                "name": item,
                "type": item_type,
                "size": item_size,
                "modified": item_modified
            })
        
        return json.dumps(result, indent=2)
        
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: Failed to list files: {str(e)}"

@mcp.tool()
def read_file(path: str) -> str:
    """Read the contents of a file.
    
    Args:
        path: The file path relative to the base directory
    """
    try:
        full_path = validate_path(path)
        
        if not os.path.exists(full_path):
            return f"Error: File '{path}' does not exist"
        
        if not os.path.isfile(full_path):
            return f"Error: '{path}' is not a file"
        
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return content
        
    except ValueError as e:
        return f"Error: {str(e)}"
    except UnicodeDecodeError:
        return f"Error: '{path}' is not a text file or has unsupported encoding"
    except Exception as e:
        return f"Error: Failed to read file: {str(e)}"

@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file with the given content.
    
    Args:
        path: The file path relative to the base directory
        content: The content to write to the file
    """
    try:
        full_path = validate_path(path)
        
        directory = os.path.dirname(full_path)
        os.makedirs(directory, exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"File '{path}' has been written successfully"
        
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: Failed to write file: {str(e)}"

@mcp.tool()
def delete_file(path: str) -> str:
    """Delete a file.
    
    Args:
        path: The file path relative to the base directory
    """
    try:
        full_path = validate_path(path)
        
        if not os.path.exists(full_path):
            return f"Error: File '{path}' does not exist"
        
        if not os.path.isfile(full_path):
            return f"Error: '{path}' is not a file"
        
        os.remove(full_path)
        return f"File '{path}' has been deleted successfully"
        
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: Failed to delete file: {str(e)}"

@mcp.tool()
def create_directory(path: str) -> str:
    """Create a directory.
    
    Args:
        path: The directory path relative to the base directory
    """
    try:
        full_path = validate_path(path)
        
        if os.path.exists(full_path):
            if os.path.isdir(full_path):
                return f"Directory '{path}' already exists"
            else:
                return f"Error: '{path}' already exists as a file"
        
        os.makedirs(full_path, exist_ok=True)
        return f"Directory '{path}' has been created successfully"
        
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: Failed to create directory: {str(e)}"

@mcp.tool()
def delete_directory(path: str, recursive: bool = False) -> str:
    """Delete a directory.
    
    Args:
        path: The directory path relative to the base directory
        recursive: Whether to delete directories recursively (default: False)
    """
    try:
        full_path = validate_path(path)
        
        if not os.path.exists(full_path):
            return f"Error: Directory '{path}' does not exist"
        
        if not os.path.isdir(full_path):
            return f"Error: '{path}' is not a directory"
        
        if recursive:
            shutil.rmtree(full_path)
        else:
            os.rmdir(full_path)
        
        return f"Directory '{path}' has been deleted successfully"
        
    except ValueError as e:
        return f"Error: {str(e)}"
    except OSError as e:
        if "not empty" in str(e):
            return f"Error: Directory '{path}' is not empty. Use recursive=True to delete non-empty directories."
        return f"Error: Failed to delete directory: {str(e)}"
    except Exception as e:
        return f"Error: Failed to delete directory: {str(e)}"

# ===== GIT OPERATIONS =====

@mcp.tool()
def git_init(subpath: str = None) -> str:
    """Initialize a git repository.
    
    Args:
        subpath: Optional subfolder path relative to base directory
    """
    result = run_git_command(["init"], subpath)
    
    if result["success"]:
        return f"✅ Git repository initialized successfully\n{result['stdout']}"
    else:
        return f"❌ Failed to initialize git repository: {result.get('error', result['stderr'])}"

@mcp.tool()
def git_status(subpath: str = None) -> str:
    """Get the status of the git repository.
    
    Args:
        subpath: Optional subfolder path relative to base directory
    """
    result = run_git_command(["status", "--porcelain"], subpath)
    
    if not result["success"]:
        return f"❌ Failed to get git status: {result.get('error', result['stderr'])}"
    
    # Parse porcelain output for better formatting
    status_lines = result["stdout"].split('\n') if result["stdout"] else []
    
    if not status_lines or not status_lines[0]:
        return "✅ Working directory is clean - no changes to commit"
    
    changes = {
        "staged": [],
        "modified": [],
        "untracked": [],
        "deleted": []
    }
    
    for line in status_lines:
        if len(line) < 3:
            continue
            
        status_code = line[:2]
        file_path = line[3:]
        
        if status_code[0] in ['A', 'M', 'D', 'R', 'C']:
            changes["staged"].append(f"{status_code[0]} {file_path}")
        elif status_code[1] == 'M':
            changes["modified"].append(file_path)
        elif status_code[1] == 'D':
            changes["deleted"].append(file_path)
        elif status_code == '??':
            changes["untracked"].append(file_path)
    
    result_text = ["📊 Git Repository Status:"]
    
    if changes["staged"]:
        result_text.append(f"\n✅ Staged for commit ({len(changes['staged'])} files):")
        for item in changes["staged"]:
            result_text.append(f"   {item}")
    
    if changes["modified"]:
        result_text.append(f"\n📝 Modified ({len(changes['modified'])} files):")
        for item in changes["modified"]:
            result_text.append(f"   {item}")
    
    if changes["deleted"]:
        result_text.append(f"\n🗑️ Deleted ({len(changes['deleted'])} files):")
        for item in changes["deleted"]:
            result_text.append(f"   {item}")
    
    if changes["untracked"]:
        result_text.append(f"\n❓ Untracked ({len(changes['untracked'])} files):")
        for item in changes["untracked"]:
            result_text.append(f"   {item}")
    
    return "\n".join(result_text)

@mcp.tool()
def git_add_files(files: List[str], subpath: str = None) -> str:
    """Add files to the git staging area.
    
    Args:
        files: List of file paths to add (use ["."] to add all files)
        subpath: Optional subfolder path relative to base directory
    """
    if not files:
        return "❌ No files specified to add"
    
    result = run_git_command(["add"] + files, subpath)
    
    if result["success"]:
        if files == ["."]:
            return "✅ All files added to staging area"
        else:
            return f"✅ Added {len(files)} file(s) to staging area: {', '.join(files)}"
    else:
        return f"❌ Failed to add files: {result.get('error', result['stderr'])}"

@mcp.tool()
def git_commit(message: str, subpath: str = None) -> str:
    """Commit staged changes to the repository.
    
    Args:
        message: Commit message
        subpath: Optional subfolder path relative to base directory
    """
    if not message.strip():
        return "❌ Commit message cannot be empty"
    
    result = run_git_command(["commit", "-m", message], subpath)
    
    if result["success"]:
        return f"✅ Changes committed successfully\n{result['stdout']}"
    else:
        error_msg = result.get('error', result['stderr'])
        if "nothing to commit" in error_msg:
            return "ℹ️ Nothing to commit - working directory is clean"
        return f"❌ Failed to commit changes: {error_msg}"

@mcp.tool()
def git_commit_all(message: str, subpath: str = None) -> str:
    """Add all changes and commit them in one operation.
    
    Args:
        message: Commit message
        subpath: Optional subfolder path relative to base directory
    """
    if not message.strip():
        return "❌ Commit message cannot be empty"
    
    # First add all files
    add_result = run_git_command(["add", "."], subpath)
    if not add_result["success"]:
        return f"❌ Failed to add files: {add_result.get('error', add_result['stderr'])}"
    
    # Then commit
    commit_result = run_git_command(["commit", "-m", message], subpath)
    
    if commit_result["success"]:
        return f"✅ All changes added and committed successfully\n{commit_result['stdout']}"
    else:
        error_msg = commit_result.get('error', commit_result['stderr'])
        if "nothing to commit" in error_msg:
            return "ℹ️ Nothing to commit - working directory is clean"
        return f"❌ Failed to commit changes: {error_msg}"

@mcp.tool()
def git_log(limit: int = 10, subpath: str = None) -> str:
    """Get commit history.
    
    Args:
        limit: Maximum number of commits to show (default: 10)
        subpath: Optional subfolder path relative to base directory
    """
    result = run_git_command([
        "log", 
        f"--max-count={limit}",
        "--pretty=format:%h|%an|%ad|%s",
        "--date=short"
    ], subpath)
    
    if not result["success"]:
        return f"❌ Failed to get commit history: {result.get('error', result['stderr'])}"
    
    if not result["stdout"]:
        return "ℹ️ No commits found in this repository"
    
    lines = result["stdout"].split('\n')
    result_text = [f"📜 Recent Commits (showing {len(lines)} of {limit} max):"]
    
    for line in lines:
        if '|' in line:
            parts = line.split('|')
            if len(parts) >= 4:
                hash_short, author, date, message = parts[0], parts[1], parts[2], '|'.join(parts[3:])
                result_text.append(f"  🔹 {hash_short} - {message}")
                result_text.append(f"     👤 {author} on {date}")
    
    return "\n".join(result_text)

@mcp.tool()
def git_show_diff(file_path: str = None, subpath: str = None) -> str:
    """Show differences in files.
    
    Args:
        file_path: Specific file to show diff for (optional - shows all if not specified)
        subpath: Optional subfolder path relative to base directory
    """
    cmd = ["diff"]
    if file_path:
        cmd.append(file_path)
    
    result = run_git_command(cmd, subpath)
    
    if not result["success"]:
        return f"❌ Failed to show diff: {result.get('error', result['stderr'])}"
    
    if not result["stdout"]:
        if file_path:
            return f"ℹ️ No changes in file: {file_path}"
        else:
            return "ℹ️ No changes in working directory"
    
    return f"📋 Git Diff:\n{result['stdout']}"

@mcp.tool()
def git_create_branch(branch_name: str, subpath: str = None) -> str:
    """Create a new git branch.
    
    Args:
        branch_name: Name of the new branch
        subpath: Optional subfolder path relative to base directory
    """
    if not branch_name.strip():
        return "❌ Branch name cannot be empty"
    
    result = run_git_command(["checkout", "-b", branch_name], subpath)
    
    if result["success"]:
        return f"✅ Created and switched to new branch: {branch_name}"
    else:
        return f"❌ Failed to create branch: {result.get('error', result['stderr'])}"

@mcp.tool()
def git_switch_branch(branch_name: str, subpath: str = None) -> str:
    """Switch to an existing git branch.
    
    Args:
        branch_name: Name of the branch to switch to
        subpath: Optional subfolder path relative to base directory
    """
    if not branch_name.strip():
        return "❌ Branch name cannot be empty"
    
    result = run_git_command(["checkout", branch_name], subpath)
    
    if result["success"]:
        return f"✅ Switched to branch: {branch_name}"
    else:
        return f"❌ Failed to switch branch: {result.get('error', result['stderr'])}"

@mcp.tool()
def git_list_branches(subpath: str = None) -> str:
    """List all git branches.
    
    Args:
        subpath: Optional subfolder path relative to base directory
    """
    result = run_git_command(["branch", "-v"], subpath)
    
    if not result["success"]:
        return f"❌ Failed to list branches: {result.get('error', result['stderr'])}"
    
    if not result["stdout"]:
        return "ℹ️ No branches found"
    
    lines = result["stdout"].split('\n')
    result_text = ["🌳 Git Branches:"]
    
    for line in lines:
        line = line.strip()
        if line:
            if line.startswith('*'):
                result_text.append(f"  ➤ {line[1:].strip()} (current)")
            else:
                result_text.append(f"    {line}")
    
    return "\n".join(result_text)

@mcp.tool()
def git_remote_info(subpath: str = None) -> str:
    """Get information about git remotes.
    
    Args:
        subpath: Optional subfolder path relative to base directory
    """
    result = run_git_command(["remote", "-v"], subpath)
    
    if not result["success"]:
        return f"❌ Failed to get remote info: {result.get('error', result['stderr'])}"
    
    if not result["stdout"]:
        return "ℹ️ No remote repositories configured"
    
    return f"🌐 Remote Repositories:\n{result['stdout']}"

# ===== DEVELOPMENT WORKFLOW HELPERS =====

@mcp.tool()
def dev_quick_save(message: str, subpath: str = None) -> str:
    """Quick development workflow: add all changes and commit with a message.
    
    This is a convenience function that combines git_add_files and git_commit.
    
    Args:
        message: Commit message for the changes
        subpath: Optional subfolder path relative to base directory
    """
    return git_commit_all(message, subpath)

@mcp.tool()
def dev_project_status(subpath: str = None) -> str:
    """Get comprehensive project status including files and git status.
    
    Args:
        subpath: Optional subfolder path relative to base directory
    """
    result_parts = []
    
    # Get file listing
    try:
        files_result = list_files(subpath or "")
        if files_result.startswith("Error:"):
            result_parts.append(f"📁 Files: {files_result}")
        else:
            files_data = json.loads(files_result)
            file_count = len([f for f in files_data if f["type"] == "file"])
            dir_count = len([f for f in files_data if f["type"] == "directory"])
            result_parts.append(f"📁 Project contains: {file_count} files, {dir_count} directories")
    except:
        result_parts.append("📁 Files: Unable to get file listing")
    
    # Get git status
    git_result = git_status(subpath)
    result_parts.append(git_result)
    
    return "\n\n".join(result_parts)

@mcp.tool()
def dev_create_project_structure(project_name: str, project_type: str = "python") -> str:
    """Create a basic project structure for common project types.
    
    Args:
        project_name: Name of the project (will create a directory with this name)
        project_type: Type of project - "python", "web", "node", or "general"
    """
    try:
        project_path = project_name
        
        # Create project directory
        create_result = create_directory(project_path)
        if create_result.startswith("Error:"):
            return create_result
        
        files_to_create = []
        
        if project_type == "python":
            files_to_create = [
                (f"{project_path}/main.py", "#!/usr/bin/env python3\n\ndef main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()\n"),
                (f"{project_path}/requirements.txt", "# Add your Python dependencies here\n"),
                (f"{project_path}/README.md", f"# {project_name}\n\nA Python project.\n\n## Installation\n\n```bash\npip install -r requirements.txt\n```\n\n## Usage\n\n```bash\npython main.py\n```\n"),
                (f"{project_path}/.gitignore", "__pycache__/\n*.pyc\n*.pyo\n*.pyd\n.Python\nbuild/\ndevelop-eggs/\ndist/\ndownloads/\neggs/\n.eggs/\nlib/\nlib64/\nparts/\nsdist/\nvar/\nwheels/\n*.egg-info/\n.installed.cfg\n*.egg\n.env\n.venv\nenv/\nvenv/\n")
            ]
        elif project_type == "web":
            files_to_create = [
                (f"{project_path}/index.html", f"<!DOCTYPE html>\n<html lang='en'>\n<head>\n    <meta charset='UTF-8'>\n    <meta name='viewport' content='width=device-width, initial-scale=1.0'>\n    <title>{project_name}</title>\n    <link rel='stylesheet' href='style.css'>\n</head>\n<body>\n    <h1>Welcome to {project_name}</h1>\n    <script src='script.js'></script>\n</body>\n</html>\n"),
                (f"{project_path}/style.css", "body {\n    font-family: Arial, sans-serif;\n    margin: 0;\n    padding: 20px;\n    background-color: #f0f0f0;\n}\n\nh1 {\n    color: #333;\n    text-align: center;\n}\n"),
                (f"{project_path}/script.js", "document.addEventListener('DOMContentLoaded', function() {\n    console.log('Page loaded successfully!');\n});\n"),
                (f"{project_path}/README.md", f"# {project_name}\n\nA web project.\n\n## Usage\n\nOpen `index.html` in your browser.\n")
            ]
        elif project_type == "node":
            files_to_create = [
                (f"{project_path}/package.json", f'{{\n  "name": "{project_name}",\n  "version": "1.0.0",\n  "description": "A Node.js project",\n  "main": "index.js",\n  "scripts": {{\n    "start": "node index.js",\n    "dev": "nodemon index.js"\n  }},\n  "dependencies": {{}},\n  "devDependencies": {{}}\n}}\n'),
                (f"{project_path}/index.js", "const express = require('express');\nconst app = express();\nconst port = 3000;\n\napp.get('/', (req, res) => {\n  res.send('Hello World!');\n});\n\napp.listen(port, () => {\n  console.log(`Server running at http://localhost:${port}`);\n});\n"),
                (f"{project_path}/README.md", f"# {project_name}\n\nA Node.js project.\n\n## Installation\n\n```bash\nnpm install\n```\n\n## Usage\n\n```bash\nnpm start\n```\n"),
                (f"{project_path}/.gitignore", "node_modules/\nnpm-debug.log*\nyarn-debug.log*\nyarn-error.log*\n.env\n.env.local\n.env.development.local\n.env.test.local\n.env.production.local\n")
            ]
        else:  # general
            files_to_create = [
                (f"{project_path}/README.md", f"# {project_name}\n\nProject description goes here.\n\n## Getting Started\n\nInstructions for getting started with this project.\n"),
                (f"{project_path}/.gitignore", ".env\n.DS_Store\nThumbs.db\n")
            ]
        
        # Create all files
        created_files = []
        for file_path, content in files_to_create:
            result = write_file(file_path, content)
            if not result.startswith("Error:"):
                created_files.append(file_path)
        
        # Initialize git repository
        git_init_result = git_init(project_path)
        
        # Create initial commit
        commit_result = git_commit_all("Initial project setup", project_path)
        
        result_text = [
            f"✅ Created {project_type} project: {project_name}",
            f"📁 Created {len(created_files)} files:",
        ]
        
        for file_path in created_files:
            result_text.append(f"   - {file_path}")
        
        result_text.extend([
            "",
            git_init_result,
            commit_result
        ])
        
        return "\n".join(result_text)
        
    except Exception as e:
        return f"❌ Failed to create project structure: {str(e)}"

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

if __name__ == "__main__":
    # Check if run with --web flag
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        # Web mode (SSE) - for Chainlit
        import uvicorn
        
        # Get port from arguments or environment or default
        port = int(os.environ.get("MCP_PORT", 8004))
        if len(sys.argv) > 2:
            try:
                port = int(sys.argv[2])
            except ValueError:
                pass
                
        print(f"Starting Web MCP Developer server on port {port}")
        print(f"Base directory: {BASE_DIR}")
        uvicorn.run(app, host="127.0.0.1", port=port)
    else:
        # STDIO mode - for Claude Desktop
        print(f"Starting STDIO MCP Developer server with base directory: {BASE_DIR}")
        mcp.run(transport='stdio')
