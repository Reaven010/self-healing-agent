import os
import json
import urllib.request
import urllib.parse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Manual fallback for .env loading
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())

CONFIG_FILE = "repositories.json"

def get_github_credentials():
    token = os.getenv("GITHUB_TOKEN")
    username = os.getenv("GITHUB_USERNAME")
    
    # Fallback: check existing repositories.json if .env is missing token/username
    if (not token or not username) and os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    first_repo = data[0]
                    if not token:
                        token = first_repo.get("github_token")
                    if not username:
                        username = first_repo.get("github_username")
        except Exception:
            pass
            
    return username, token

def fetch_all_github_repos(username, token=None):
    """
    Fetches all repositories for the specified GitHub user or authenticated token using GitHub API v3 with pagination.
    """
    repos = []
    page = 1
    per_page = 100

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Self-Healing-Agent-Python"
    }
    if token:
        headers["Authorization"] = f"token {token}"
        url_template = f"https://api.github.com/user/repos?per_page={per_page}&page={{page}}&type=all"
    else:
        url_template = f"https://api.github.com/users/{username}/repos?per_page={per_page}&page={{page}}"

    while True:
        url = url_template.format(page=page)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    print(f"Error fetching repos from GitHub API (HTTP {response.status})")
                    break
                data = json.loads(response.read().decode('utf-8'))
                if not data:
                    break
                repos.extend(data)
                if len(data) < per_page:
                    break
                page += 1
        except Exception as e:
            print(f"Exception while contacting GitHub API: {e}")
            break

    return repos

def sync_repositories_config(config_file=CONFIG_FILE, username=None, token=None, default_base_dir=None):
    """
    Synchronizes repositories.json with all repositories found in the user's GitHub profile.
    Preserves custom user configuration fields (such as 'server', 'deploy_path', custom 'log_file').
    """
    if not username or not token:
        env_user, env_token = get_github_credentials()
        username = username or env_user
        token = token or env_token

    if not username:
        print("Error: GitHub username is not provided and could not be found in .env or repositories.json.")
        return []

    if not default_base_dir:
        default_base_dir = os.path.abspath("repository")

    os.makedirs(default_base_dir, exist_ok=True)

    print(f"Fetching GitHub repositories for profile '{username}'...")
    api_repos = fetch_all_github_repos(username, token)
    if not api_repos:
        print("No repositories fetched from GitHub API.")
        return []

    print(f"Discovered {len(api_repos)} repositories on GitHub profile '{username}'.")

    # Load existing configs
    existing_configs = []
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                existing_configs = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read existing {config_file}: {e}")

    # Build mapping by lowercased repo name or github url
    existing_map = {}
    for item in existing_configs:
        name_key = item.get("name", "").strip().lower()
        url_key = item.get("github_url", "").strip().lower()
        if name_key:
            existing_map[name_key] = item
        if url_key:
            existing_map[url_key] = item

    updated_configs = []

    for repo in api_repos:
        r_name = repo.get("name")
        r_url = repo.get("clone_url")
        
        name_key = r_name.strip().lower() if r_name else ""
        url_key = r_url.strip().lower() if r_url else ""

        # Check if already configured
        existing_item = existing_map.get(name_key) or existing_map.get(url_key)

        if existing_item:
            # Preserve existing configuration while ensuring token/url are present
            cfg = dict(existing_item)
            if token and not cfg.get("github_token"):
                cfg["github_token"] = token
            if username and not cfg.get("github_username"):
                cfg["github_username"] = username
            if r_url and not cfg.get("github_url"):
                cfg["github_url"] = r_url
            
            # Normalize clone_path & log_file if path contains Windows drive letters on Linux, or Linux paths on Windows
            if os.name != "nt" and cfg.get("clone_path") and (":" in cfg["clone_path"] or "\\" in cfg["clone_path"]):
                local_repo_dir = os.path.join(default_base_dir, r_name)
                cfg["clone_path"] = local_repo_dir
                if "log_file" in cfg and (":" in cfg["log_file"] or "\\" in cfg["log_file"]) and "server" not in cfg:
                    cfg["log_file"] = os.path.join(local_repo_dir, "app.log")
            elif os.name == "nt" and cfg.get("clone_path") and cfg["clone_path"].startswith("/home/"):
                local_repo_dir = os.path.join(default_base_dir, r_name)
                cfg["clone_path"] = local_repo_dir
                if "log_file" in cfg and cfg["log_file"].startswith("/home/") and "server" not in cfg:
                    cfg["log_file"] = os.path.join(local_repo_dir, "app.log")
            
            updated_configs.append(cfg)
        else:
            # Create default configuration entry
            local_repo_dir = os.path.join(default_base_dir, r_name)
            cfg = {
                "name": r_name,
                "github_url": r_url,
                "github_token": token or "",
                "github_username": username or "",
                "clone_path": local_repo_dir,
                "log_file": os.path.join(local_repo_dir, "app.log")
            }
            updated_configs.append(cfg)


    # Save back to config_file
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(updated_configs, f, indent=2)
        print(f"Successfully synchronized {len(updated_configs)} repositories to '{config_file}'.")
    except Exception as e:
        print(f"Error saving updated configurations to '{config_file}': {e}")

    return updated_configs

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Synchronize all GitHub profile repositories into repositories.json")
    parser.add_argument("--username", help="GitHub Username")
    parser.add_argument("--token", help="GitHub Personal Access Token")
    parser.add_argument("--output", default=CONFIG_FILE, help="Path to config file (default: repositories.json)")
    args = parser.parse_args()

    sync_repositories_config(config_file=args.output, username=args.username, token=args.token)
