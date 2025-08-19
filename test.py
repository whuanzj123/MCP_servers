import subprocess

# Run the WSL docker ps command
result = subprocess.run(["wsl", "docker", "ps"], capture_output=True, text=True)
print(result.stdout)