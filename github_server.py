from mcp.server.fastmcp import FastMCP, Context
import os
import json
import datetime
import re
import base64
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
import sys
from typing import List, Dict, Any, Optional
from github import Github, GithubException
from github.Repository import Repository
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.ContentFile import ContentFile
from dotenv import load_dotenv
import time

# Load environment variables from .env file
load_dotenv()

# Get GitHub token from environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("Warning: GITHUB_TOKEN not found in environment variables. Some functionality will be limited.")

# Initialize GitHub API client
try:
    g = Github(GITHUB_TOKEN)
    # Test the connection by getting the authenticated user
    user = g.get_user()
    print(f"Connected to GitHub as: {user.login}")
except Exception as e:
    print(f"Error initializing GitHub client: {str(e)}")
    # Initialize with a None value that we'll check before operations
    g = None

# Create an MCP server
mcp = FastMCP("GitHubTools")

# --- Helper functions ---

def get_repo(repo_name: str) -> Repository:
    """
    Get a repository by name.
    Handles both format: "owner/repo" and just "repo" for the authenticated user's repos
    """
    if "/" not in repo_name:
        # If only repo name is provided, assume it's the authenticated user's repo
        return g.get_user().get_repo(repo_name)
    else:
        # Otherwise, it's in the format "owner/repo"
        return g.get_repo(repo_name)

def format_issue(issue: Issue) -> Dict[str, Any]:
    """Format an issue object into a dictionary for easier JSON serialization"""
    return {
        "number": issue.number,
        "title": issue.title,
        "state": issue.state,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
        "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
        "body": issue.body,
        "url": issue.html_url,
        "user": issue.user.login if issue.user else None,
        "labels": [label.name for label in issue.labels],
        "assignees": [assignee.login for assignee in issue.assignees],
        "comments": issue.comments
    }

def format_pull_request(pr: PullRequest) -> Dict[str, Any]:
    """Format a pull request object into a dictionary for easier JSON serialization"""
    return {
        "number": pr.number,
        "title": pr.title,
        "state": pr.state,
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
        "closed_at": pr.closed_at.isoformat() if pr.closed_at else None,
        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
        "body": pr.body,
        "url": pr.html_url,
        "user": pr.user.login if pr.user else None,
        "head": pr.head.ref,
        "base": pr.base.ref,
        "mergeable": pr.mergeable,
        "draft": pr.draft
    }

def format_repo(repo: Repository) -> Dict[str, Any]:
    """Format a repository object into a dictionary for easier JSON serialization"""
    return {
        "name": repo.name,
        "full_name": repo.full_name,
        "description": repo.description,
        "url": repo.html_url,
        "stars": repo.stargazers_count,
        "forks": repo.forks_count,
        "open_issues": repo.open_issues_count,
        "private": repo.private,
        "default_branch": repo.default_branch,
        "language": repo.language,
        "created_at": repo.created_at.isoformat() if repo.created_at else None,
        "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
        "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None
    }

# --- Repository Tools ---

@mcp.tool()
def list_repos(visibility: str = "all", max_count: int = 10) -> str:
    """
    List repositories for the authenticated user.
    
    Args:
        visibility: Filter by visibility - "all", "public", or "private"
        max_count: Maximum number of repositories to return
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        # Validate visibility parameter
        if visibility not in ["all", "public", "private"]:
            return f"Error: Invalid visibility parameter. Must be 'all', 'public', or 'private'."
        
        # Get list of repositories
        user = g.get_user()
        if visibility == "all":
            repos = user.get_repos()
        elif visibility == "public":
            repos = user.get_repos(visibility="public")
        else:  # private
            repos = user.get_repos(visibility="private")
        
        # Format and return repository data
        result = []
        for repo in repos[:max_count]:
            result.append(format_repo(repo))
            
        return json.dumps(result, indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error listing repositories: {str(e)}"

@mcp.tool()
def get_repo_info(repo_name: str) -> str:
    """
    Get detailed information about a repository.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        return json.dumps(format_repo(repo), indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error getting repository info: {str(e)}"

@mcp.tool()
def list_branches(repo_name: str, max_count: int = 20) -> str:
    """
    List branches in a repository.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        max_count: Maximum number of branches to return
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        branches = list(repo.get_branches()[:max_count])
        
        result = []
        for branch in branches:
            result.append({
                "name": branch.name,
                "protected": branch.protected,
                "commit_sha": branch.commit.sha if branch.commit else None
            })
            
        return json.dumps(result, indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error listing branches: {str(e)}"

# --- File Operations ---

@mcp.tool()
def list_files(repo_name: str, path: str = "", branch: str = None) -> str:
    """
    List files and directories in a repository path.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        path: Directory path within the repository
        branch: Branch name (default: repository's default branch)
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        contents = repo.get_contents(path, ref=branch)
        
        result = []
        # Handle case where contents is a single file
        if not isinstance(contents, list):
            contents = [contents]
            
        for content in contents:
            result.append({
                "name": content.name,
                "path": content.path,
                "type": "file" if content.type == "file" else "directory",
                "size": content.size if content.type == "file" else None,
                "url": content.html_url
            })
            
        return json.dumps(sorted(result, key=lambda x: (x["type"], x["name"])), indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error listing files: {str(e)}"

@mcp.tool()
def get_file_content(repo_name: str, file_path: str, branch: str = None) -> str:
    """
    Get the content of a file from a repository.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        file_path: Path to the file within the repository
        branch: Branch name (default: repository's default branch)
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        content_file = repo.get_contents(file_path, ref=branch)
        
        # Handle binary files vs text files
        if isinstance(content_file, list):
            return "Error: Path is a directory, not a file."
            
        if content_file.size > 1000000:  # 1MB limit
            return f"Error: File is too large to display ({content_file.size} bytes)"
            
        try:
            # Try to decode as text - this will work for most code files
            content = base64.b64decode(content_file.content).decode('utf-8')
            return content
        except UnicodeDecodeError:
            # If it fails, it's likely a binary file
            return f"Binary file: {content_file.name} ({content_file.size} bytes)"
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error getting file content: {str(e)}"

@mcp.tool()
def create_file(repo_name: str, file_path: str, content: str, commit_message: str, branch: str = None) -> str:
    """
    Create a new file in a repository.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        file_path: Path where the file should be created
        content: Content of the file
        commit_message: Commit message for the creation
        branch: Branch name (default: repository's default branch)
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        
        # Check if file already exists
        try:
            repo.get_contents(file_path, ref=branch)
            return f"Error: File already exists at {file_path}"
        except GithubException as e:
            if e.status != 404:  # If error is not "Not Found"
                raise
        
        # Create the file
        result = repo.create_file(
            path=file_path,
            message=commit_message,
            content=content,
            branch=branch
        )
        
        return json.dumps({
            "file": {
                "path": file_path,
                "url": result["content"].html_url
            },
            "commit": {
                "sha": result["commit"].sha,
                "message": result["commit"].message,
                "url": result["commit"].html_url
            }
        }, indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error creating file: {str(e)}"

@mcp.tool()
def update_file(repo_name: str, file_path: str, content: str, commit_message: str, branch: str = None) -> str:
    """
    Update an existing file in a repository.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        file_path: Path to the file to update
        content: New content of the file
        commit_message: Commit message for the update
        branch: Branch name (default: repository's default branch)
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        
        # Get the current file to get its SHA
        file = repo.get_contents(file_path, ref=branch)
        
        # Update the file
        result = repo.update_file(
            path=file_path,
            message=commit_message,
            content=content,
            sha=file.sha,
            branch=branch
        )
        
        return json.dumps({
            "file": {
                "path": file_path,
                "url": result["content"].html_url
            },
            "commit": {
                "sha": result["commit"].sha,
                "message": result["commit"].message,
                "url": result["commit"].html_url
            }
        }, indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error updating file: {str(e)}"

# --- Issue and PR Tools ---

@mcp.tool()
def list_issues(repo_name: str, state: str = "open", max_count: int = 10) -> str:
    """
    List issues in a repository.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        state: Filter by state - "open", "closed", or "all"
        max_count: Maximum number of issues to return
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        # Validate state parameter
        if state not in ["open", "closed", "all"]:
            return f"Error: Invalid state parameter. Must be 'open', 'closed', or 'all'."
            
        repo = get_repo(repo_name)
        issues = repo.get_issues(state=state)
        
        result = []
        for issue in issues[:max_count]:
            # Skip pull requests (they are also returned as issues by the API)
            if issue.pull_request:
                continue
                
            result.append(format_issue(issue))
            
        return json.dumps(result, indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error listing issues: {str(e)}"

@mcp.tool()
def get_issue(repo_name: str, issue_number: int) -> str:
    """
    Get details of a specific issue.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        issue_number: Issue number
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        issue = repo.get_issue(number=issue_number)
        
        # Check if it's actually a pull request
        if issue.pull_request:
            return f"Error: Issue #{issue_number} is actually a pull request. Use get_pull_request instead."
            
        return json.dumps(format_issue(issue), indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error getting issue: {str(e)}"

@mcp.tool()
def create_issue(repo_name: str, title: str, body: str, labels: List[str] = None) -> str:
    """
    Create a new issue in a repository.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        title: Issue title
        body: Issue body/description
        labels: List of labels to apply to the issue
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        
        # Create the issue
        issue = repo.create_issue(
            title=title,
            body=body,
            labels=labels
        )
        
        return json.dumps(format_issue(issue), indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error creating issue: {str(e)}"

@mcp.tool()
def list_pull_requests(repo_name: str, state: str = "open", max_count: int = 10) -> str:
    """
    List pull requests in a repository.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        state: Filter by state - "open", "closed", or "all"
        max_count: Maximum number of pull requests to return
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        # Validate state parameter
        if state not in ["open", "closed", "all"]:
            return f"Error: Invalid state parameter. Must be 'open', 'closed', or 'all'."
            
        repo = get_repo(repo_name)
        pulls = repo.get_pulls(state=state)
        
        result = []
        for pr in pulls[:max_count]:
            result.append(format_pull_request(pr))
            
        return json.dumps(result, indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error listing pull requests: {str(e)}"

@mcp.tool()
def get_pull_request(repo_name: str, pr_number: int) -> str:
    """
    Get details of a specific pull request.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        pr_number: Pull request number
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        pr = repo.get_pull(number=pr_number)
        
        return json.dumps(format_pull_request(pr), indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error getting pull request: {str(e)}"

@mcp.tool()
def create_pull_request(repo_name: str, title: str, body: str, head: str, base: str = "main", draft: bool = False) -> str:
    """
    Create a new pull request.
    
    Args:
        repo_name: Repository name (format: "owner/repo" or just "repo" for your own repos)
        title: Pull request title
        body: Pull request body/description
        head: The branch containing the changes (e.g., "feature-branch")
        base: The branch to merge into (default: "main")
        draft: Whether to create a draft PR
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        repo = get_repo(repo_name)
        
        # Create the pull request
        pr = repo.create_pull(
            title=title,
            body=body,
            head=head,
            base=base,
            draft=draft
        )
        
        return json.dumps(format_pull_request(pr), indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error creating pull request: {str(e)}"

# --- Repository Resources ---

@mcp.resource("github://repo/{repo_name}")
def repo_resource(repo_name: str) -> str:
    """
    Get repository information as a resource.
    
    Args:
        repo_name: Repository name (format: "owner/repo")
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        # Replace URL-encoded slashes with actual slashes
        repo_name = repo_name.replace("%2F", "/")
        
        repo = get_repo(repo_name)
        return json.dumps(format_repo(repo), indent=2)
    except Exception as e:
        return f"Error fetching repository resource: {str(e)}"

@mcp.resource("github://file/{repo_name}/{file_path}")
def file_resource(repo_name: str, file_path: str) -> str:
    """
    Get file content as a resource.
    
    Args:
        repo_name: Repository name (format: "owner/repo")
        file_path: Path to the file within the repository
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        # Replace URL-encoded slashes with actual slashes
        repo_name = repo_name.replace("%2F", "/")
        file_path = file_path.replace("%2F", "/")
        
        repo = get_repo(repo_name)
        content_file = repo.get_contents(file_path)
        
        if isinstance(content_file, list):
            return f"Error: Path is a directory, not a file: {file_path}"
            
        if content_file.size > 1000000:  # 1MB limit
            return f"Error: File is too large to display ({content_file.size} bytes)"
            
        try:
            # Try to decode as text - this will work for most code files
            content = base64.b64decode(content_file.content).decode('utf-8')
            return content
        except UnicodeDecodeError:
            # If it fails, it's likely a binary file
            return f"Binary file: {content_file.name} ({content_file.size} bytes)"
    except Exception as e:
        return f"Error fetching file resource: {str(e)}"

@mcp.resource("github://readme/{repo_name}")
def readme_resource(repo_name: str) -> str:
    """
    Get repository README as a resource.
    
    Args:
        repo_name: Repository name (format: "owner/repo")
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        # Replace URL-encoded slashes with actual slashes
        repo_name = repo_name.replace("%2F", "/")
        
        repo = get_repo(repo_name)
        readme = repo.get_readme()
        
        try:
            content = base64.b64decode(readme.content).decode('utf-8')
            return content
        except UnicodeDecodeError:
            return f"Error: Unable to decode README content"
    except GithubException as e:
        if e.status == 404:
            return f"No README found in repository {repo_name}"
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error fetching README resource: {str(e)}"

# --- Search Tools ---

@mcp.tool()
def search_code(query: str, max_count: int = 10) -> str:
    """
    Search for code across GitHub.
    
    Args:
        query: Search query (GitHub code search syntax)
        max_count: Maximum number of results to return
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        search_results = g.search_code(query=query)
        
        result = []
        for item in search_results[:max_count]:
            result.append({
                "repository": item.repository.full_name,
                "path": item.path,
                "name": item.name,
                "url": item.html_url,
                "score": item.score
            })
            
        return json.dumps(result, indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error searching code: {str(e)}"

@mcp.tool()
def search_repositories(query: str, max_count: int = 10) -> str:
    """
    Search for repositories across GitHub.
    
    Args:
        query: Search query (GitHub repository search syntax)
        max_count: Maximum number of results to return
    """
    try:
        if not g:
            return "Error: GitHub client not initialized. Please check your GITHUB_TOKEN."
            
        search_results = g.search_repositories(query=query)
        
        result = []
        for item in search_results[:max_count]:
            result.append(format_repo(item))
            
        return json.dumps(result, indent=2)
    except GithubException as e:
        return f"GitHub API Error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error searching repositories: {str(e)}"

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
        port = int(os.environ.get("MCP_PORT", 8003))
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