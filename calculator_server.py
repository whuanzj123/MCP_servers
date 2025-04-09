from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.middleware.cors import CORSMiddleware
import sys
import os
# Create an MCP server
mcp = FastMCP("Calculator")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b
@mcp.tool()
def subtract(a: int, b: int) -> int:
    """Subtract b from a"""
    return a - b
@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b
@mcp.tool()
def divide(a: int, b: int) -> float:
    """Divide a by b"""
    if b == 0:
        return "Error: Cannot divide by zero"
    return a / b

# Create Starlette application with the MCP SSE app mounted at the root
app = Starlette(
    routes=[
        Mount('/', app=mcp.sse_app()),
    ]
)

# Add CORS middleware to allow cross-origin requests (important for Chainlit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[""],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=[""],
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