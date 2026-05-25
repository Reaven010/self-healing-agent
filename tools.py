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

def get_target_path(file_path: str = "") -> str:
    """
    Resolves the directory path of the target file.
    Prepend target repository base directory.
    """
    repo_base = "."
    if _active_repo:
        repo_base = _active_repo.get("repo_path", ".")
        
    if not file_path:
        return repo_base
        
    # Check if target is a remote repository using UNIX paths
    if _active_repo and "server" in _active_repo:
        if file_path.startswith("/") or ":" in file_path:
            return file_path
        # Clean trailing slash and combine
        return f"{repo_base.rstrip('/')}/{file_path}"
    
    # Local pathing
    return os.path.join(repo_base, file_path) if not os.path.isabs(file_path) else file_path

def get_ssh_client_for_config(repo_config):
    """
    Establishes an SSH connection to the remote server configured in repo_config.
    Returns None if the repository is local.
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

def get_ssh_client():
    """
    Establishes an SSH connection to the remote server if one is configured in _active_repo.
    """
    return get_ssh_client_for_config(_active_repo)

@tool("Run Pytest Tool")
def run_pytest(test_path: str = ".") -> str:
    """
    Runs pytest on the specified path inside the target repository and returns the output.
    If the tests pass, it returns the success output.
    If the tests fail, it returns the error output.
    """
    try:
        repo_path = get_target_path()
        ssh = get_ssh_client()
        if ssh:
            try:
                # Execute tests on the remote server
                cmd = f"cd {repo_path} && pytest {test_path}"
                stdin, stdout, stderr = ssh.exec_command(cmd)
                output = stdout.read().decode("utf-8") + "\n" + stderr.read().decode("utf-8")
                ssh.close()
                return output
            except Exception as ssh_err:
                ssh.close()
                raise ssh_err
        else:
            result = subprocess.run(
                ["pytest", test_path],
                capture_output=True,
                text=True,
                cwd=repo_path # Run tests inside local target repository
            )
            output = result.stdout + "\n" + result.stderr
            return output
    except Exception as e:
        return f"Error running tests: {str(e)}"

@tool("Git Commit Tool")
def git_commit_tool(commit_message: str) -> str:
    """
    Stages all modified files, commits them with the given message, and
    pushes the changes to the remote repository (GitHub) if configured.
    """
    try:
        repo_path = get_target_path()
        ssh = get_ssh_client()
        if ssh:
            try:
                # Stage and commit remotely
                escaped_msg = commit_message.replace('"', '\\"')
                cmd = f'cd {repo_path} && git add -u && git commit -m "{escaped_msg}"'
                stdin, stdout, stderr = ssh.exec_command(cmd)
                commit_out = stdout.read().decode("utf-8") + "\n" + stderr.read().decode("utf-8")
                
                # Check for remotes on the server and try pushing
                stdin, stdout, stderr = ssh.exec_command(f"cd {repo_path} && git remote")
                remotes = stdout.read().decode("utf-8").strip()
                push_status = ""
                if remotes:
                    stdin, stdout, stderr = ssh.exec_command(f"cd {repo_path} && git push")
                    push_out = stdout.read().decode("utf-8") + "\n" + stderr.read().decode("utf-8")
                    if "rejected" in push_out or "error" in push_out:
                        push_status = f" but failed to push to remote: {push_out}"
                    else:
                        push_status = " and successfully pushed to remote (GitHub)"
                else:
                    push_status = " (no remote repository configured, committed locally on remote server)"
                
                ssh.close()
                return f"Successfully committed remotely: {commit_out}{push_status}"
            except Exception as ssh_err:
                ssh.close()
                raise ssh_err
        else:
            repo = Repo(repo_path)
            repo.git.add(u=True) # Add all modified tracked files in the target repo
            repo.index.commit(commit_message)
            
            # Try pushing to remote if a remote is configured
            push_status = ""
            if repo.remotes:
                try:
                    # Push active branch to the configured remote
                    origin = repo.remotes[0]
                    origin.push()
                    push_status = " and successfully pushed to remote (GitHub)"
                except Exception as push_err:
                    push_status = f" but failed to push to remote: {str(push_err)}"
            else:
                push_status = " (no remote repository configured, committed locally)"

            return f"Successfully committed with message: {commit_message}{push_status}"
    except Exception as e:
        return f"Failed to commit: {str(e)}"

@tool("Read File Tool")
def read_file_tool(file_path: str) -> str:
    """
    Reads the content of a specified file inside the target repository.
    """
    try:
        full_path = get_target_path(file_path)
        ssh = get_ssh_client()
        if ssh:
            try:
                sftp = ssh.open_sftp()
                with sftp.open(full_path, "r") as f:
                    content = f.read().decode("utf-8")
                sftp.close()
                ssh.close()
                return content
            except Exception as ssh_err:
                ssh.close()
                raise ssh_err
        else:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        return f"Failed to read file {file_path}: {str(e)}"

@tool("Write File Tool")
def write_file_tool(input_data: str) -> str:
    """
    Writes content to a file inside the target repository.
    The input_data MUST be a string formatted exactly as:
    file_path|||file_content
    """
    try:
        file_path, content = input_data.split("|||", 1)
        full_path = get_target_path(file_path.strip())
        ssh = get_ssh_client()
        if ssh:
            try:
                sftp = ssh.open_sftp()
                # Create parent directories remotely if they don't exist
                parent_dir = os.path.dirname(full_path)
                try:
                    sftp.mkdir(parent_dir)
                except:
                    pass
                with sftp.open(full_path, "w") as f:
                    f.write(content)
                sftp.close()
                ssh.close()
                return f"Successfully wrote to remote file {file_path}"
            except Exception as ssh_err:
                ssh.close()
                raise ssh_err
        else:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Failed to write file: {str(e)}. Make sure input is 'path|||content'."
