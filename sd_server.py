from mcp.server.fastmcp import FastMCP
import requests
import base64
import json
import os
import sys
import datetime
from typing import Optional, Dict, Any
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

# Configuration
WEBUI_BASE_URL = "http://127.0.0.1:7860"  # Default stable-diffusion-webui URL
OUTPUT_DIR = r"C:/Users/Administrator/Desktop/TestField/sd_outputs"  # Directory to save generated images

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Create an MCP server
mcp = FastMCP("StableDiffusion")

def check_webui_connection() -> bool:
    """Check if the stable-diffusion-webui is running and accessible."""
    try:
        response = requests.get(f"{WEBUI_BASE_URL}/sdapi/v1/sd-models", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def save_image_from_base64(base64_data: str, filename: str) -> str:
    """Save a base64 image to the output directory."""
    try:
        # Remove data URL prefix if present
        if base64_data.startswith('data:image'):
            base64_data = base64_data.split(',')[1]
        
        # Decode base64 data
        image_data = base64.b64decode(base64_data)
        
        # Full path for the image
        full_path = os.path.join(OUTPUT_DIR, filename)
        
        # Save the image
        with open(full_path, 'wb') as f:
            f.write(image_data)
        
        return full_path
    except Exception as e:
        raise Exception(f"Failed to save image: {str(e)}")

@mcp.tool()
def txt2img(
    prompt: str,
    negative_prompt: str = "",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg_scale: float = 7.0,
    seed: int = -1,
    sampler_name: str = "Euler",
    save_image: bool = True
) -> str:
    """Generate an image from text using stable-diffusion-webui.
    
    Args:
        prompt: The text prompt describing the image to generate
        negative_prompt: Text describing what should not be in the image (default: "")
        width: Image width in pixels (default: 512)
        height: Image height in pixels (default: 512)
        steps: Number of denoising steps (default: 20)
        cfg_scale: Classifier-free guidance scale (default: 7.0)
        seed: Random seed for reproducible results (-1 for random, default: -1)
        sampler_name: Sampling method (default: "Euler")
        save_image: Whether to save the image to disk (default: True)
    """
    try:
        # Check if webui is running
        if not check_webui_connection():
            return "Error: stable-diffusion-webui is not running or not accessible at " + WEBUI_BASE_URL
        
        # Prepare the request payload
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "seed": seed,
            "sampler_name": sampler_name,
            "batch_size": 1,
            "n_iter": 1,
            "restore_faces": False,
            "tiling": False,
            "enable_hr": False,
            "save_images": False,  # We'll handle saving ourselves
            "send_images": True,
            "do_not_save_samples": True,
            "do_not_save_grid": True
        }
        
        # Make the API request
        response = requests.post(
            f"{WEBUI_BASE_URL}/sdapi/v1/txt2img",
            json=payload,
            timeout=300  # 5 minutes timeout for generation
        )
        
        if response.status_code != 200:
            return f"Error: API request failed with status {response.status_code}: {response.text}"
        
        # Parse the response
        try:
            result = response.json()
        except json.JSONDecodeError:
            return f"Error: Invalid JSON response from webui: {response.text[:200]}"
        
        if not result.get("images"):
            return "Error: No images were generated"
        
        # Get the first generated image
        image_base64 = result["images"][0]
        
        # Generate filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sd_{timestamp}.png"
        
        # Parse the info field safely
        info_data = {}
        if "info" in result:
            try:
                if isinstance(result["info"], str):
                    info_data = json.loads(result["info"])
                else:
                    info_data = result["info"]
            except (json.JSONDecodeError, TypeError):
                info_data = {}
        
        # Get the actual seed used
        actual_seed = info_data.get("seed", seed)
        
        if save_image:
            # Save the image
            saved_path = save_image_from_base64(image_base64, filename)
            
            # Prepare result info
            result_info = {
                "status": "success",
                "image_saved": True,
                "image_path": saved_path,
                "filename": filename,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "parameters": {
                    "width": width,
                    "height": height,
                    "steps": steps,
                    "cfg_scale": cfg_scale,
                    "seed": actual_seed,
                    "sampler": sampler_name
                }
            }
            
            return json.dumps(result_info, indent=2)
        else:
            # Return just the base64 data and metadata
            result_info = {
                "status": "success",
                "image_saved": False,
                "image_base64": image_base64[:100] + "...",  # Truncated for display
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "parameters": {
                    "width": width,
                    "height": height,
                    "steps": steps,
                    "cfg_scale": cfg_scale,
                    "seed": actual_seed,
                    "sampler": sampler_name
                }
            }
            
            return json.dumps(result_info, indent=2)
        
    except requests.exceptions.Timeout:
        return "Error: Request timed out. Image generation took too long."
    except requests.exceptions.RequestException as e:
        return f"Error: Network request failed: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def get_models() -> str:
    """Get a list of available Stable Diffusion models from the webui."""
    try:
        if not check_webui_connection():
            return "Error: stable-diffusion-webui is not running or not accessible at " + WEBUI_BASE_URL
        
        response = requests.get(f"{WEBUI_BASE_URL}/sdapi/v1/sd-models", timeout=10)
        
        if response.status_code != 200:
            return f"Error: API request failed with status {response.status_code}"
        
        models = response.json()
        
        # Format the models list
        model_list = []
        for model in models:
            model_info = {
                "title": model.get("title", "Unknown"),
                "model_name": model.get("model_name", "Unknown"),
                "filename": model.get("filename", "Unknown"),
                "config": model.get("config", "Unknown")
            }
            model_list.append(model_info)
        
        return json.dumps(model_list, indent=2)
        
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def get_samplers() -> str:
    """Get a list of available sampling methods from the webui."""
    try:
        if not check_webui_connection():
            return "Error: stable-diffusion-webui is not running or not accessible at " + WEBUI_BASE_URL
        
        response = requests.get(f"{WEBUI_BASE_URL}/sdapi/v1/samplers", timeout=10)
        
        if response.status_code != 200:
            return f"Error: API request failed with status {response.status_code}"
        
        samplers = response.json()
        
        # Extract sampler names
        sampler_names = [sampler.get("name", "Unknown") for sampler in samplers]
        
        return json.dumps(sampler_names, indent=2)
        
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def get_webui_status() -> str:
    """Check the status of the stable-diffusion-webui connection."""
    try:
        if check_webui_connection():
            # Get some basic info
            models_response = requests.get(f"{WEBUI_BASE_URL}/sdapi/v1/sd-models", timeout=5)
            if models_response.status_code == 200:
                models = models_response.json()
                current_model = next((m["title"] for m in models if m.get("model_name") == models[0].get("model_name")), "Unknown")
            else:
                current_model = "Unable to determine"
            
            status_info = {
                "status": "connected",
                "webui_url": WEBUI_BASE_URL,
                "current_model": current_model,
                "output_directory": OUTPUT_DIR,
                "api_available": True
            }
        else:
            status_info = {
                "status": "disconnected",
                "webui_url": WEBUI_BASE_URL,
                "current_model": "N/A",
                "output_directory": OUTPUT_DIR,
                "api_available": False,
                "message": "Please ensure stable-diffusion-webui is running with --api flag"
            }
        
        return json.dumps(status_info, indent=2)
        
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def set_webui_url(url: str) -> str:
    """Change the stable-diffusion-webui URL.
    
    Args:
        url: The new URL for the webui (e.g., "http://127.0.0.1:7860")
    """
    global WEBUI_BASE_URL
    
    # Remove trailing slash if present
    url = url.rstrip('/')
    
    # Basic URL validation
    if not url.startswith(('http://', 'https://')):
        return "Error: URL must start with http:// or https://"
    
    old_url = WEBUI_BASE_URL
    WEBUI_BASE_URL = url
    
    # Test the new connection
    if check_webui_connection():
        return f"Successfully changed webui URL from {old_url} to {WEBUI_BASE_URL}"
    else:
        WEBUI_BASE_URL = old_url  # Revert on failure
        return f"Error: Could not connect to webui at {url}. Reverted to {old_url}"

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
        # Web mode (SSE) - for Chainlit or other web interfaces
        import uvicorn
        
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
        print("Starting STDIO MCP server for Stable Diffusion")
        mcp.run(transport='stdio')