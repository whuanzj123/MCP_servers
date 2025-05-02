from mcp.server.fastmcp import FastMCP, Context
import os
import json
import datetime
import re
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
import sys

# Hardcoded paths for security (restrict access to only these directories)
CONFIG_PATH = "/Users/huanwei/Library/Application Support/Claude/claude_desktop_config.json"
LOGS_DIR = "/Users/huanwei/Library/Logs/Claude"

# Create an MCP server
mcp = FastMCP("ClaudeConfigTools")

# --- Config File Management Tools ---

@mcp.tool()
def read_config() -> str:
    """Read the current Claude Desktop configuration file."""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                config_data = json.load(f)
            return json.dumps(config_data, indent=2)
        else:
            return f"Error: Config file not found at {CONFIG_PATH}"
    except Exception as e:
        return f"Error reading config file: {str(e)}"

@mcp.tool()
def write_config(config_json: str) -> str:
    """Update the Claude Desktop configuration file.
    
    Args:
        config_json: JSON string with complete configuration
    """
    try:
        # Validate JSON
        try:
            config_data = json.loads(config_json)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON format - {str(e)}"
        
        # Create backup of current config
        if os.path.exists(CONFIG_PATH):
            backup_path = f"{CONFIG_PATH}.bak.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
            with open(CONFIG_PATH, 'r') as src:
                with open(backup_path, 'w') as dst:
                    dst.write(src.read())
        
        # Write new config
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return f"Configuration updated successfully. Backup created at {backup_path}"
    except Exception as e:
        return f"Error updating config file: {str(e)}"

@mcp.tool()
def update_config_property(property_path: str, value: str) -> str:
    """Update a specific property in the Claude Desktop configuration.
    
    Args:
        property_path: Path to the property (e.g., "servers.myserver.command")
        value: New value for the property (will be parsed as JSON if possible)
    """
    try:
        # Read current config
        if not os.path.exists(CONFIG_PATH):
            return f"Error: Config file not found at {CONFIG_PATH}"
        
        with open(CONFIG_PATH, 'r') as f:
            config_data = json.load(f)
        
        # Create backup
        backup_path = f"{CONFIG_PATH}.bak.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        with open(backup_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        # Parse the property path
        parts = property_path.split('.')
        
        # Try to parse value as JSON, fall back to string if not valid JSON
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = value
        
        # Navigate to the right spot in the config
        current = config_data
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Last part - set the value
                current[part] = parsed_value
            else:
                # Create nested dicts if they don't exist
                if part not in current:
                    current[part] = {}
                current = current[part]
        
        # Write updated config
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return f"Property {property_path} updated successfully. Backup created at {backup_path}"
    except Exception as e:
        return f"Error updating config property: {str(e)}"

# --- Log File Management Tools ---

@mcp.tool()
def list_log_files() -> str:
    """List all available log files in the Claude Desktop logs directory."""
    try:
        if not os.path.exists(LOGS_DIR):
            return f"Error: Logs directory not found at {LOGS_DIR}"
        
        log_files = []
        for filename in os.listdir(LOGS_DIR):
            if filename.endswith('.log'):
                file_path = os.path.join(LOGS_DIR, filename)
                size = os.path.getsize(file_path)
                modified = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                log_files.append({
                    "filename": filename,
                    "size_bytes": size,
                    "modified": modified.strftime("%Y-%m-%d %H:%M:%S")
                })
        
        return json.dumps(log_files, indent=2)
    except Exception as e:
        return f"Error listing log files: {str(e)}"

@mcp.tool()
def read_log_file(filename: str, max_lines: int = 100) -> str:
    """Read contents of a specific log file.
    
    Args:
        filename: Name of the log file (e.g., "mcp.log")
        max_lines: Maximum number of lines to read from the end of the file
    """
    try:
        # Validate filename to prevent directory traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            return "Error: Invalid filename"
        
        # Only allow .log files
        if not filename.endswith('.log'):
            return "Error: Only .log files are allowed"
        
        file_path = os.path.join(LOGS_DIR, filename)
        
        if not os.path.exists(file_path):
            return f"Error: Log file not found: {filename}"
        
        # Read the last max_lines lines from the file
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            
        # Get the last max_lines
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
            
        return ''.join(lines)
    except Exception as e:
        return f"Error reading log file: {str(e)}"

@mcp.tool()
def search_logs(pattern: str, max_results: int = 100) -> str:
    """Search across all log files for a specific pattern.
    
    Args:
        pattern: Regular expression pattern to search for
        max_results: Maximum number of matching lines to return
    """
    try:
        if not os.path.exists(LOGS_DIR):
            return f"Error: Logs directory not found at {LOGS_DIR}"
        
        results = []
        for filename in os.listdir(LOGS_DIR):
            if filename.endswith('.log'):
                file_path = os.path.join(LOGS_DIR, filename)
                
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    for line_num, line in enumerate(f, 1):
                        if re.search(pattern, line):
                            results.append({
                                "file": filename,
                                "line": line_num,
                                "content": line.strip()
                            })
                            
                            if len(results) >= max_results:
                                break
                
                if len(results) >= max_results:
                    break
        
        if results:
            return json.dumps(results, indent=2)
        else:
            return f"No matches found for pattern: {pattern}"
    except Exception as e:
        return f"Error searching log files: {str(e)}"

@mcp.tool()
def tail_mcp_logs(lines: int = 50) -> str:
    """Read the last lines from MCP logs.
    
    This is a convenience function to quickly access recent MCP logs.
    
    Args:
        lines: Number of lines to read from the end of the file
    """
    try:
        log_files = []
        for filename in os.listdir(LOGS_DIR):
            if filename.startswith('mcp') and filename.endswith('.log'):
                log_files.append(filename)
        
        if not log_files:
            return "No MCP log files found"
        
        # Find the most recent log file
        log_files.sort(key=lambda f: os.path.getmtime(os.path.join(LOGS_DIR, f)), reverse=True)
        latest_log = log_files[0]
        
        return f"Contents of {latest_log} (last {lines} lines):\n\n" + read_log_file(latest_log, lines)
    except Exception as e:
        return f"Error reading MCP logs: {str(e)}"

# --- Resource Endpoints ---

@mcp.resource("claude://config")
def get_config_resource() -> str:
    """Provide the Claude Desktop configuration as a resource."""
    try:
        with open(CONFIG_PATH, 'r') as f:
            config_data = json.load(f)
        return json.dumps(config_data, indent=2)
    except Exception as e:
        return f"Error reading config: {str(e)}"

@mcp.resource("claude://logs/{filename}")
def get_log_resource(filename: str) -> str:
    """Provide a specific log file as a resource."""
    # Validate filename
    if '..' in filename or '/' in filename or '\\' in filename:
        return "Error: Invalid filename"
    
    # Only allow .log files
    if not filename.endswith('.log'):
        return "Error: Only .log files are allowed"
    
    file_path = os.path.join(LOGS_DIR, filename)
    
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        else:
            return f"Error: Log file not found: {filename}"
    except Exception as e:
        return f"Error reading log file: {str(e)}"

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
        port = int(os.environ.get("MCP_PORT", 8002))
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