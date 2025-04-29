"""
MCP Documentation Server

This MCP server exposes documentation and information about the Model Context Protocol (MCP)
to help LLMs quickly understand MCP concepts. It provides resources and tools to access
documentation from the MCP_prompt folder.
"""

import os
import sys
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from mcp.server.fastmcp import FastMCP, Context

# Configure paths
ROOT_DIR = Path(__file__).parent.absolute()
MCP_DOCS_DIR = Path(ROOT_DIR.parent, "MCP_prompt").absolute()

# Check if the docs directory exists
if not MCP_DOCS_DIR.exists():
    print(f"Error: MCP documentation directory not found: {MCP_DOCS_DIR}")
    print("Please ensure the MCP_prompt folder is in the correct location.")
    sys.exit(1)

print(f"Using MCP documentation from: {MCP_DOCS_DIR}")

# Create an MCP server
mcp = FastMCP("mcp-docs")

# Dictionary to store cached content
CONTENT_CACHE = {}

def read_file_content(file_path: Path) -> str:
    """Read and cache file content"""
    if str(file_path) in CONTENT_CACHE:
        return CONTENT_CACHE[str(file_path)]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            CONTENT_CACHE[str(file_path)] = content
            return content
    except Exception as e:
        return f"Error reading file: {str(e)}"

def get_file_list(directory: Path) -> List[Dict[str, Any]]:
    """Get a list of files in a directory with metadata"""
    files = []
    
    try:
        for item in directory.iterdir():
            if item.is_file():
                files.append({
                    "name": item.name,
                    "path": str(item.relative_to(MCP_DOCS_DIR)),
                    "type": "file",
                    "size": item.stat().st_size,
                })
            elif item.is_dir() and not item.name.startswith('.'):
                files.append({
                    "name": item.name,
                    "path": str(item.relative_to(MCP_DOCS_DIR)),
                    "type": "directory",
                })
    except Exception as e:
        print(f"Error listing files: {str(e)}")
    
    return sorted(files, key=lambda x: (x['type'], x['name']))

def search_file_content(query: str, content: str) -> List[str]:
    """Search for query in content and return matching lines with context"""
    if not query or not content:
        return []
    
    lines = content.split('\n')
    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    
    for i, line in enumerate(lines):
        if pattern.search(line):
            # Get context (lines before and after)
            start = max(0, i - 2)
            end = min(len(lines), i + 3)
            
            # Format the matching lines with context
            context = lines[start:end]
            context_str = "\n".join(context)
            
            # Add line numbers
            line_info = f"[Lines {start+1}-{end}]"
            
            # Add to results
            results.append(f"{line_info}\n{context_str}")
    
    return results

# Resource: list of available files
@mcp.resource("mcp://files")
def get_files() -> str:
    """List all available MCP documentation files"""
    files = get_file_list(MCP_DOCS_DIR)
    
    result = ["# Available MCP Documentation Files", ""]
    
    for file in files:
        if file["type"] == "file":
            size_kb = file["size"] / 1024
            result.append(f"- 📄 `{file['path']}` ({size_kb:.1f} KB)")
        else:
            result.append(f"- 📁 `{file['path']}/`")
    
    return "\n".join(result)

# Resource: MCP overview
@mcp.resource("mcp://overview")
def get_overview() -> str:
    """Provide an overview of Model Context Protocol"""
    return """# Model Context Protocol (MCP) Overview

The Model Context Protocol (MCP) is a standardized way for applications to provide context, resources, and tools to Large Language Models (LLMs). It separates the concerns of providing context from the actual LLM interaction.

## Key Components

1. **Resources**: Expose data to LLMs (similar to GET endpoints)
   - Files, database records, API responses, live system data
   - Application-controlled (client decides when to use them)
   - Identified by unique URIs

2. **Tools**: Allow LLMs to take actions (similar to POST endpoints)
   - Execute commands, call APIs, transform data
   - Model-controlled (LLM can decide when to use them)
   - Include input schemas for validation

3. **Prompts**: Reusable templates for LLM interactions
   - Pre-defined conversation flows
   - Accept dynamic arguments
   - User-controlled (surface as UI elements)

4. **Architecture**:
   - Client-server model
   - Hosts (LLM applications like Claude Desktop)
   - Clients maintain 1:1 connections with servers
   - Servers provide context, tools, and prompts

5. **Transports**: Communication mechanisms
   - Standard Input/Output (stdio)
   - Server-Sent Events (SSE)
   - WebSockets

MCP enables powerful integrations between LLMs and external systems while maintaining security through human-in-the-loop controls and clear capability declarations.
"""

# Resource: MCP concepts (mapped to specific file)
@mcp.resource("mcp://concepts/{concept}")
def get_concept(concept: str) -> str:
    """Get documentation for a specific MCP concept"""
    concept_map = {
        "resources": "llms-full.txt#Resources",
        "tools": "llms-full.txt#Tools",
        "prompts": "llms-full.txt#Prompts",
        "architecture": "llms-full.txt#Core architecture",
        "sampling": "llms-full.txt#Sampling",
        "transports": "llms-full.txt#Transports"
    }
    
    if concept not in concept_map:
        return f"Unknown concept: {concept}. Available concepts: {', '.join(concept_map.keys())}"
    
    file_section = concept_map[concept].split('#')
    file_name = file_section[0]
    section = file_section[1] if len(file_section) > 1 else None
    
    file_path = Path(MCP_DOCS_DIR, file_name)
    if not file_path.exists():
        return f"Documentation file not found: {file_name}"
    
    content = read_file_content(file_path)
    
    if section:
        # Find the section in the content
        section_pattern = re.compile(f"# {re.escape(section)}\n")
        match = section_pattern.search(content)
        
        if match:
            # Find the end of the section (next section or end of file)
            start_pos = match.start()
            next_section = re.search(r"# [A-Za-z]", content[start_pos+1:])
            
            if next_section:
                end_pos = start_pos + 1 + next_section.start()
                return content[start_pos:end_pos].strip()
            else:
                return content[start_pos:].strip()
    
    return content

# Resource: File content by path
@mcp.resource("mcp://file/{file_path:path}")
def get_file(file_path: str) -> str:
    """Get content of a specific MCP documentation file"""
    try:
        # Sanitize the file path to prevent directory traversal
        safe_path = Path(file_path).parts
        file_path = Path(MCP_DOCS_DIR, *safe_path)
        
        # Check if the file exists and is within MCP_DOCS_DIR
        if not file_path.exists():
            return f"File not found: {file_path}"
        
        if not str(file_path).startswith(str(MCP_DOCS_DIR)):
            return "Access denied: Path is outside the documentation directory"
        
        if file_path.is_dir():
            # If it's a directory, list its contents
            files = get_file_list(file_path)
            
            result = [f"# Directory: {file_path.relative_to(MCP_DOCS_DIR)}", ""]
            
            for file in files:
                if file["type"] == "file":
                    size_kb = file["size"] / 1024
                    result.append(f"- 📄 `{file['path']}` ({size_kb:.1f} KB)")
                else:
                    result.append(f"- 📁 `{file['path']}/`")
            
            return "\n".join(result)
        
        # Read and return the file content
        return read_file_content(file_path)
        
    except Exception as e:
        return f"Error accessing file: {str(e)}"

# Tool: Search for MCP concepts
@mcp.tool()
def search_mcp_docs(query: str, ctx: Context = None) -> str:
    """
    Search MCP documentation for a specific term or concept
    
    Args:
        query: Search term to look for in the documentation
        
    Returns:
        Matching sections from the documentation
    """
    if not query or len(query) < 3:
        return "Please provide a search term with at least 3 characters."
    
    try:
        results = []
        
        # Search through all files in the MCP_DOCS_DIR
        for root, _, files in os.walk(MCP_DOCS_DIR):
            for file in files:
                if file.endswith(('.txt', '.md', '.py')) and not file.startswith('.'):
                    file_path = Path(root, file)
                    
                    # Don't search in very large files
                    if file_path.stat().st_size > 10 * 1024 * 1024:  # 10 MB limit
                        if ctx:
                            ctx.warning(f"Skipping large file: {file_path.relative_to(MCP_DOCS_DIR)}")
                        continue
                    
                    relative_path = file_path.relative_to(MCP_DOCS_DIR)
                    content = read_file_content(file_path)
                    
                    # Search for matches in content
                    matches = search_file_content(query, content)
                    
                    if matches:
                        results.append(f"## File: {relative_path}")
                        results.append(f"Found {len(matches)} matches:\n")
                        
                        for i, match in enumerate(matches[:5], 1):  # Limit to first 5 matches
                            results.append(f"### Match {i}:")
                            results.append(match)
                            results.append("")
                        
                        if len(matches) > 5:
                            results.append(f"... and {len(matches) - 5} more matches.")
                        
                        results.append("")
        
        if not results:
            return f"No matches found for '{query}' in MCP documentation."
        
        return "\n".join(results)
        
    except Exception as e:
        error_message = f"Error searching MCP documentation: {str(e)}"
        if ctx:
            ctx.error(error_message)
        return error_message

# Tool: Get MCP concept
@mcp.tool()
def get_mcp_concept(concept: str, ctx: Context = None) -> str:
    """
    Get documentation for a specific MCP concept
    
    Args:
        concept: Name of the concept (resources, tools, prompts, architecture, sampling, transports)
        
    Returns:
        Documentation for the requested concept
    """
    try:
        concepts = [
            "resources", "tools", "prompts", 
            "architecture", "sampling", "transports"
        ]
        
        if concept.lower() not in concepts:
            return f"Unknown concept: {concept}. Available concepts: {', '.join(concepts)}"
        
        return get_concept(concept.lower())
        
    except Exception as e:
        error_message = f"Error retrieving MCP concept: {str(e)}"
        if ctx:
            ctx.error(error_message)
        return error_message

# Tool: List Python SDK examples
@mcp.tool()
def list_python_sdk_examples(ctx: Context = None) -> str:
    """
    List example code from the Python SDK
    
    Returns:
        List of available examples
    """
    try:
        examples_dir = Path(MCP_DOCS_DIR, "python-sdk", "examples")
        if not examples_dir.exists():
            return "Python SDK examples directory not found."
        
        result = ["# Python SDK Examples", ""]
        
        # List all example directories
        for item in examples_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                result.append(f"## {item.name}")
                
                # List files in the directory
                example_files = []
                for file in item.iterdir():
                    if file.is_file() and file.suffix == '.py':
                        size_kb = file.stat().st_size / 1024
                        example_files.append(f"- `{file.name}` ({size_kb:.1f} KB)")
                
                if example_files:
                    result.extend(example_files)
                    result.append("")
                else:
                    result.append("No Python examples found.")
                    result.append("")
        
        if len(result) <= 2:
            return "No Python SDK examples found."
        
        return "\n".join(result)
        
    except Exception as e:
        error_message = f"Error listing Python SDK examples: {str(e)}"
        if ctx:
            ctx.error(error_message)
        return error_message

# Tool: Get SDK example code
@mcp.tool()
def get_sdk_example(
    example_type: str = "fastmcp", 
    example_name: str = "simple_echo.py",
    ctx: Context = None
) -> str:
    """
    Get specific example code from the SDK
    
    Args:
        example_type: Type of example (fastmcp, clients, servers)
        example_name: Name of the example file
        
    Returns:
        Source code of the requested example
    """
    try:
        examples_dir = Path(MCP_DOCS_DIR, "python-sdk", "examples", example_type)
        if not examples_dir.exists():
            return f"Example directory not found: {example_type}"
        
        example_path = examples_dir / example_name
        if not example_path.exists():
            # List available examples
            available = [f.name for f in examples_dir.iterdir() if f.is_file() and f.suffix == '.py']
            return f"Example '{example_name}' not found in {example_type}. Available examples: {', '.join(available)}"
        
        content = read_file_content(example_path)
        return f"# {example_name}\n\n```python\n{content}\n```"
        
    except Exception as e:
        error_message = f"Error retrieving example code: {str(e)}"
        if ctx:
            ctx.error(error_message)
        return error_message

if __name__ == "__main__":
    print("Starting MCP Documentation Server")
    print(f"MCP documentation directory: {MCP_DOCS_DIR}")
    
    # Check if docs directory contains expected files
    llms_full_path = Path(MCP_DOCS_DIR, "llms-full.txt")
    if not llms_full_path.exists():
        print(f"Warning: Expected documentation file not found: {llms_full_path}")
    
    python_sdk_path = Path(MCP_DOCS_DIR, "python-sdk")
    if not python_sdk_path.exists():
        print(f"Warning: Python SDK directory not found: {python_sdk_path}")
    
    # Run the server
    mcp.run(transport='stdio')
