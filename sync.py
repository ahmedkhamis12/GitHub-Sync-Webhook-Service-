
from flask import Flask, request
import subprocess
import os
import docker
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
client = docker.from_env()  # Connect to Docker daemon

# Helper function to extract repository name from its Git URL
def extract_repo_name(repo_url):
    if not repo_url:
        return None
    # Example: "git@github.com:user/odoo-project.git" -> "odoo-project"
    return repo_url.split("/")[-1].replace(".git", "")

# Dictionary to hold repository configurations
REPOS = {}

# Read repository names from the REPOS environment variable (comma-separated)
repo_names = os.getenv("REPOS", "").split(",")

# Loop through each repo name and build its config from .env variables
for name in repo_names:
    name = name.strip()
    repo_url = os.getenv(f"REPO_URL_{name}")
    repo_label = os.getenv(f"CONTAINER_LABEL_{name}")
    base_dir = os.getenv("REPOS_BASE_DIR", "/repos")  # default fallback
    repo_dir = f"{base_dir}/{extract_repo_name(repo_url)}" if repo_url else None


    # Add repo config only if all required fields are present
    if repo_url and repo_label and repo_dir:
        REPOS[name] = {
            "url": repo_url,
            "dir": repo_dir,
            "label": repo_label
        }

# Clone or pull the Git repository
def pull_repo(repo_dir, repo_url):
    if not os.path.isdir(repo_dir):
        print(f"Cloning repo {repo_url} into {repo_dir}")
        subprocess.run(["git", "clone", repo_url, repo_dir], check=True)
    else:
        print(f"Pulling latest changes in {repo_dir}")
        subprocess.run(["git", "-C", repo_dir, "pull"], check=True)

# Restart all Docker containers that have a specific label
def restart_containers(label):
    containers = client.containers.list(filters={"label": label})
    if not containers:
        print(f"No containers found with label: {label}")
    for container in containers:
        print(f"Restarting container {container.name}")
        container.restart()

# Webhook endpoint to trigger repo update and container restart
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    repo_name = data.get('repository', {}).get('name')

    # Validate if the repo is supported
    if not repo_name or repo_name not in REPOS:
        return "Repository not supported", 400

    repo_info = REPOS[repo_name]

    try:
        # Pull latest changes and restart relevant containers
        pull_repo(repo_info["dir"], repo_info["url"])
        restart_containers(repo_info["label"])
    except subprocess.CalledProcessError as e:
        return f"Git command failed: {str(e)}", 500
    except Exception as e:
        return f"Error: {str(e)}", 500

    return f"Updated and restarted containers for {repo_name}", 200

# Start the Flask server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
