import os
import subprocess
from crewai.tools import tool
from git import Repo

@tool("Run Pytest Tool")
def run_pytest(test_path: str = ".") -> str:
    """
    Runs pytest on the specified path and returns the output.
    If the tests pass, it returns the success output.
    If the tests fail, it returns the error output.
    """
    try:
        result = subprocess.run(
            ["pytest", test_path],
            capture_output=True,
            text=True
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
        repo = Repo(".")
        repo.git.add(u=True) # Add all modified tracked files
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
    Reads the content of a specified file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Failed to read file {file_path}: {str(e)}"

@tool("Write File Tool")
def write_file_tool(input_data: str) -> str:
    """
    Writes content to a file. 
    The input_data MUST be a string formatted exactly as:
    file_path|||file_content
    """
    try:
        file_path, content = input_data.split("|||", 1)
        with open(file_path.strip(), "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Failed to write file: {str(e)}. Make sure input is 'path|||content'."
