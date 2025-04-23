from mcp.server.fastmcp import FastMCP
import os
import sys
import datetime
import json
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
import shutil
# Set the base directory to restrict file operations
BASE_DIR = r"C:/Users/Administrator/Desktop/TestField"

# Ensure base directory exists
os.makedirs(BASE_DIR, exist_ok=True)

# Create an MCP server
mcp = FastMCP("FileSystem")

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

@mcp.tool()
def copy_file(source_path: str, destination_path: str) -> str:
    """Copy a file from one location to another.
    
    Args:
        source_path: The source file path relative to the base directory
        destination_path: The destination path relative to the base directory
    """
    try:
        # Validate and get the full paths
        source_full_path = validate_path(source_path)
        destination_full_path = validate_path(destination_path)
        
        # Check if the source file exists
        if not os.path.exists(source_full_path):
            return f"Error: Source file '{source_path}' does not exist"
        
        # Check if the source is a file
        if not os.path.isfile(source_full_path):
            return f"Error: Source '{source_path}' is not a file"
            
        # Ensure the destination directory exists
        destination_dir = os.path.dirname(destination_full_path)
        os.makedirs(destination_dir, exist_ok=True)
        
        # Check if destination already exists
        if os.path.exists(destination_full_path):
            return f"Error: Destination '{destination_path}' already exists"
        
        # Copy the file with metadata (timestamps, permissions)
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
        # Validate and get the full path
        full_path = validate_path(directory)
        
        # Check if the directory exists
        if not os.path.exists(full_path):
            return f"Error: Directory '{directory}' does not exist"
        
        # Check if it's a directory
        if not os.path.isdir(full_path):
            return f"Error: '{directory}' is not a directory"
        
        # Get the list of files and directories
        items = os.listdir(full_path)
        
        # Build the result
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
        # Validate and get the full path
        full_path = validate_path(path)
        
        # Check if the file exists
        if not os.path.exists(full_path):
            return f"Error: File '{path}' does not exist"
        
        # Check if it's a file
        if not os.path.isfile(full_path):
            return f"Error: '{path}' is not a file"
        
        # Read the file content
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
        # Validate and get the full path
        full_path = validate_path(path)
        
        # Ensure the directory exists
        directory = os.path.dirname(full_path)
        os.makedirs(directory, exist_ok=True)
        
        # Write the content to the file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"File '{path}' has been written successfully"
        
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: Failed to write file: {str(e)}"

# @mcp.tool()
# def append_file(path: str, content: str) -> str:
#     """Append content to an existing file.
    
#     Args:
#         path: The file path relative to the base directory
#         content: The content to append to the file
#     """
#     try:
#         # Validate and get the full path
#         full_path = validate_path(path)
        
#         # Check if the file exists
#         file_exists = os.path.exists(full_path) and os.path.isfile(full_path)
        
#         # Ensure the directory exists
#         directory = os.path.dirname(full_path)
#         os.makedirs(directory, exist_ok=True)
        
#         # Append the content to the file
#         with open(full_path, 'a', encoding='utf-8') as f:
#             f.write(content)
        
#         action = "appended to" if file_exists else "created and written to"
#         return f"File '{path}' has been {action} successfully"
        
#     except ValueError as e:
#         return f"Error: {str(e)}"
#     except Exception as e:
#         return f"Error: Failed to append to file: {str(e)}"

@mcp.tool()
def delete_file(path: str) -> str:
    """Delete a file.
    
    Args:
        path: The file path relative to the base directory
    """
    try:
        # Validate and get the full path
        full_path = validate_path(path)
        
        # Check if the file exists
        if not os.path.exists(full_path):
            return f"Error: File '{path}' does not exist"
        
        # Check if it's a file
        if not os.path.isfile(full_path):
            return f"Error: '{path}' is not a file"
        
        # Delete the file
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
        # Validate and get the full path
        full_path = validate_path(path)
        
        # Check if the directory already exists
        if os.path.exists(full_path):
            if os.path.isdir(full_path):
                return f"Directory '{path}' already exists"
            else:
                return f"Error: '{path}' already exists as a file"
        
        # Create the directory
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
        # Validate and get the full path
        full_path = validate_path(path)
        
        # Check if the directory exists
        if not os.path.exists(full_path):
            return f"Error: Directory '{path}' does not exist"
        
        # Check if it's a directory
        if not os.path.isdir(full_path):
            return f"Error: '{path}' is not a directory"
        
        # Delete the directory
        if recursive:
            import shutil
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

@mcp.tool()
def file_info(path: str) -> str:
    """Get information about a file or directory.
    
    Args:
        path: The path relative to the base directory
    """
    try:
        # Validate and get the full path
        full_path = validate_path(path)
        
        # Check if the path exists
        if not os.path.exists(full_path):
            return f"Error: '{path}' does not exist"
        
        # Get file/directory information
        info = {
            "name": os.path.basename(full_path),
            "path": path,
            "type": "directory" if os.path.isdir(full_path) else "file",
            "exists": os.path.exists(full_path),
            "size": os.path.getsize(full_path) if os.path.isfile(full_path) else None,
            "created": datetime.datetime.fromtimestamp(
                os.path.getctime(full_path)
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "modified": datetime.datetime.fromtimestamp(
                os.path.getmtime(full_path)
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "accessed": datetime.datetime.fromtimestamp(
                os.path.getatime(full_path)
            ).strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        return json.dumps(info, indent=2)
        
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: Failed to get file info: {str(e)}"

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