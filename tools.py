import os
import subprocess
import paramiko
from crewai.tools import tool
from git import Repo

# Holds the active repository configuration context for the current self-healing run
_active_repo = None

def set_active_repo(config):
    """
    Sets the active repository configuration context.
    Called before the CrewAI workflow starts.
    """
    global _active_repo
    _active_repo = config
    # Ensure local workspace copy is fully prepared and synced
    prepare_local_workspace()

def prepare_local_workspace():
    """
    Clones the GitHub repository locally inside the configured clone_path (or fallback to 'workspace/<repo_name>')
    after performing a fresh clean of the target folder.
    """
    if not _active_repo or "github_url" not in _active_repo:
        return
        
    local_path = get_target_path()
    repo_name = _active_repo.get("name", "temp_repo").replace(" ", "_").lower()
    
    # Inject username and token into the HTTPS GitHub URL for seamless authentication
    github_url = _active_repo["github_url"]
    username = _active_repo.get("github_username")
    token = _active_repo.get("github_token")
    
    auth_url = github_url
    if username and token:
        if github_url.startswith("https://"):
            auth_url = github_url.replace("https://", f"https://{username}:{token}@")
            
    if os.path.exists(local_path):
        print(f"[{repo_name}] Path '{local_path}' already exists. Deleting it for a fresh clone...")
        import shutil
        import time
        # Try a few times in case of locked files
        for i in range(3):
            try:
                shutil.rmtree(local_path)
                break
            except Exception as e:
                if i == 2:
                    print(f"[{repo_name}] Warning: could not delete existing path: {e}")
                else:
                    time.sleep(1)

    print(f"[{repo_name}] Cloning GitHub repository locally to '{local_path}'...")
    try:
        Repo.clone_from(auth_url, local_path)
        print(f"[{repo_name}] Clone successful.")
    except Exception as e:
        print(f"[{repo_name}] Error cloning repository: {e}")

def get_target_path(file_path: str = "") -> str:
    """
    Resolves the directory path of the target file inside the local workspace copy.
    All agent actions (read, write, test) run locally inside the workspace.
    """
    if _active_repo and "clone_path" in _active_repo:
        local_repo_base = os.path.abspath(_active_repo["clone_path"])
    else:
        repo_name = "temp_repo"
        if _active_repo:
            repo_name = _active_repo.get("name", "temp_repo").replace(" ", "_").lower()
        workspace_dir = os.path.abspath("repository")
        local_repo_base = os.path.join(workspace_dir, repo_name)
    
    if not file_path:
        return local_repo_base
        
    return os.path.join(local_repo_base, file_path) if not os.path.isabs(file_path) else file_path

def get_ssh_client_for_config(repo_config):
    """
    Establishes an SSH connection to the remote server configured in repo_config.
    Used to pull deployments remotely on the hosted server.
    """
    if not repo_config or "server" not in repo_config:
        return None
    
    server_conf = repo_config["server"]
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    host = server_conf.get("host")
    user = server_conf.get("user")
    port = int(server_conf.get("port", 22))
    
    # Authenticate using private key or password
    if "key_path" in server_conf:
        key_path = server_conf["key_path"]
        private_key = paramiko.RSAKey.from_private_key_file(key_path)
        ssh.connect(host, port=port, username=user, pkey=private_key)
    elif "password" in server_conf:
        password = server_conf["password"]
        ssh.connect(host, port=port, username=user, password=password)
    else:
        ssh.connect(host, port=port, username=user)
        
    return ssh

def deploy_to_remote_server():
    """
    SSHs into the remote hosted server and pulls the latest changes from GitHub inside the deploy_path directory.
    This applies the agent's verified fix live!
    """
    if not _active_repo or "server" not in _active_repo:
        return "Local repository, skipping remote deployment."
        
    deploy_path = _active_repo.get("deploy_path")
    if not deploy_path:
        return "No remote deploy_path configured, skipping deployment."
        
    print(f"[{_active_repo.get('name')}] Triggering remote server deployment Git pull at '{_active_repo['server'].get('host')}'...")
    try:
        ssh = get_ssh_client_for_config(_active_repo)
        # Pull latest changes on remote server
        cmd = f"cd {deploy_path} && git pull"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        deploy_out = stdout.read().decode("utf-8") + "\n" + stderr.read().decode("utf-8")
        ssh.close()
        return f"\n\n🚀 Remote Deployment Success:\n{deploy_out.strip()}"
    except Exception as e:
        return f"\n\n⚠️ Remote Deployment Failed: {str(e)}"

@tool("Run Pytest Tool")
def run_pytest(test_path: str = ".") -> str:
    """
    Runs pytest on the specified path inside the local workspace repository and returns the output.
    If the tests pass, it returns the success output.
    If the tests fail, it returns the error output.
    """
    try:
        local_repo_path = get_target_path()
        result = subprocess.run(
            ["pytest", test_path],
            capture_output=True,
            text=True,
            cwd=local_repo_path # Run tests locally in the workspace clone folder
        )
        output = result.stdout + "\n" + result.stderr
        return output
    except Exception as e:
        return f"Error running tests: {str(e)}"

@tool("Git Commit Tool")
def git_commit_tool(commit_message: str) -> str:
    """
    Stages all modified files, commits them with the given message, and
    pushes the changes back to your GitHub repository before auto-deploying to the server.
    """
    try:
        local_repo_path = get_target_path()
        repo = Repo(local_repo_path)
        repo.git.add(u=True) # Add all modified tracked files
        repo.index.commit(commit_message)
        
        # Push to remote GitHub
        push_status = ""
        if repo.remotes:
            try:
                # Push active branch to GitHub using injected credential URL
                origin = repo.remotes.origin
                origin.push()
                push_status = " and successfully pushed back to GitHub"
            except Exception as push_err:
                push_status = f" but failed to push to GitHub: {str(push_err)}"
        else:
            push_status = " (no GitHub remote configured, committed locally)"

        # Trigger automatic remote server Git pull deployment
        deploy_status = deploy_to_remote_server()

        return f"Successfully committed with message: {commit_message}{push_status}{deploy_status}"
    except Exception as e:
        return f"Failed to commit: {str(e)}"

@tool("Read File Tool")
def read_file_tool(file_path: str) -> str:
    """
    Reads the content of a specified file inside the local workspace repository.
    """
    try:
        full_path = get_target_path(file_path)
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Failed to read file {file_path}: {str(e)}"

@tool("Write File Tool")
def write_file_tool(input_data: str) -> str:
    """
    Writes content to a file inside the local workspace repository.
    The input_data MUST be a string formatted exactly as:
    file_path|||file_content
    """
    try:
        file_path, content = input_data.split("|||", 1)
        full_path = get_target_path(file_path.strip())
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to local file {file_path}"
    except Exception as e:
        return f"Failed to write file: {str(e)}. Make sure input is 'path|||content'."
