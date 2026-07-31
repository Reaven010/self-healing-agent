import os
import sys
import time
import json
import argparse
import datetime
from git import Repo

# Ensure sys.stdout handles UTF-8 on Windows and Linux
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from repo_discovery import sync_repositories_config, CONFIG_FILE

def get_authenticated_url(github_url, token):
    if not token or not github_url or "@" in github_url:
        return github_url
    if github_url.startswith("https://"):
        return github_url.replace("https://", f"https://x-access-token:{token}@")
    return github_url

def count_commits_today(repo_path="."):
    """
    Counts the number of commits made today (since 00:00:00 local time).
    """
    try:
        repo = Repo(repo_path)
        today_midnight = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        commits = list(repo.iter_commits(since=today_midnight.isoformat()))
        return len(commits), repo
    except Exception as e:
        print(f"Error accessing git repo at '{repo_path}': {e}")
        return 0, None

def update_readme_activity(repo_path, commit_num, total_needed):
    """
    Updates or appends a timestamped line to README.md to ensure a valid file change.
    """
    readme_path = os.path.join(repo_path, "README.md")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    activity_header = "## Daily Activity Log\n"
    new_entry = f"- [{now_str}] Automated activity update ({commit_num}/{total_needed})\n"
    
    content = ""
    if os.path.exists(readme_path):
        for enc in ["utf-8", "utf-8-sig", "utf-16", "latin-1"]:
            try:
                with open(readme_path, "r", encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        else:
            with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
        if activity_header.strip() not in content:
            content += f"\n\n{activity_header}{new_entry}"
        else:
            content += new_entry
    else:
        content = f"# Repository\n\n{activity_header}{new_entry}"
        
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)

def ensure_local_repo(repo_config):
    """
    Ensures local clone directory exists and git repository is present.
    """
    clone_path = repo_config.get("clone_path") or repo_config.get("repo_path") or "."
    github_url = repo_config.get("github_url")
    token = repo_config.get("github_token")

    if os.path.exists(clone_path) and os.path.exists(os.path.join(clone_path, ".git")):
        try:
            repo = Repo(clone_path)
            if github_url and token and repo.remotes:
                try:
                    auth_url = get_authenticated_url(github_url, token)
                    repo.remotes.origin.set_url(auth_url)
                except Exception:
                    pass
            if repo.remotes:
                try:
                    repo.remotes.origin.pull()
                except Exception:
                    pass
            return clone_path
        except Exception:
            pass

    if github_url:
        os.makedirs(os.path.dirname(os.path.abspath(clone_path)), exist_ok=True)
        auth_url = get_authenticated_url(github_url, token)
        print(f"Cloning '{repo_config.get('name')}' to '{clone_path}'...")
        try:
            repo = Repo.clone_from(auth_url, clone_path)
            print(f"  -> Successfully cloned '{repo_config.get('name')}'.")
            return clone_path
        except Exception as e:
            print(f"  -> Failed to clone '{repo_config.get('name')}': {e}")
            return None
    return clone_path if os.path.exists(clone_path) else None

def make_daily_commits(repo_path=".", min_commits=10, push=True, repo_config=None):
    """
    Ensures that at least min_commits are present for today.
    """
    commits_today, repo = count_commits_today(repo_path)
    if repo is None:
        return
        
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Target repo: '{repo_path}' | Commits today: {commits_today} | Target minimum: {min_commits}")
    
    if commits_today >= min_commits:
        print(f"[OK] Goal achieved! Today's commits ({commits_today}) meet or exceed minimum ({min_commits}). No automated commits needed.")
        return
        
    needed = min_commits - commits_today
    print(f"Need {needed} more commit(s) today to meet minimum {min_commits} commits goal.")
    
    for i in range(1, needed + 1):
        commit_count_now = commits_today + i
        print(f"\nMaking automated commit {i}/{needed} (Daily total: {commit_count_now}/{min_commits})...")
        
        # 1. Update README.md
        update_readme_activity(repo_path, i, needed)
        
        # 2. Stage changes
        repo.git.add("README.md")
        
        # 3. Commit
        commit_msg = f"docs: daily activity log update [{commit_count_now}/{min_commits} minimum goal]"
        repo.index.commit(commit_msg)
        print(f"  -> Committed: '{commit_msg}'")
        
        # 4. Push to remote if configured and requested
        if push:
            if repo.remotes:
                try:
                    if repo_config and repo_config.get("github_url") and repo_config.get("github_token"):
                        auth_url = get_authenticated_url(repo_config["github_url"], repo_config["github_token"])
                        repo.remotes.origin.set_url(auth_url)
                    repo.remotes.origin.push()
                    print("  -> Successfully pushed to GitHub remote.")
                except Exception as push_err:
                    if "403" in str(push_err):
                        print(f"  -> Push warning (HTTP 403): Token lacks write access ('Contents: Read and write'). Committed locally.")
                    else:
                        print(f"  -> Push warning: {push_err}")
            else:
                print("  -> No remote origin configured. Committed locally.")

                
        # Brief pause between commits for distinct timestamps
        time.sleep(1)

    final_count, _ = count_commits_today(repo_path)
    print(f"\nFinished! Today's daily commit count is now {final_count} (minimum goal: {min_commits}).")

def process_all_profile_repos(config_file=CONFIG_FILE, min_commits=10, push=True, check_only=False, sync=False):
    if sync:
        sync_repositories_config(config_file=config_file)

    if not os.path.exists(config_file):
        print(f"Error: Configuration file '{config_file}' not found.")
        return

    with open(config_file, 'r', encoding='utf-8') as f:
        repo_configs = json.load(f)

    print(f"\n--- Processing {len(repo_configs)} profile repositories for daily commit tracking ---\n")
    for idx, cfg in enumerate(repo_configs, 1):
        name = cfg.get("name", f"Repo-{idx}")
        print(f"\n[{idx}/{len(repo_configs)}] Processing profile repository: '{name}'")
        
        target_path = ensure_local_repo(cfg)
        if not target_path:
            print(f"Skipping repository '{name}' due to path/clone issues.")
            continue

        if check_only:
            count, _ = count_commits_today(target_path)
            print(f"  -> Commits today in '{name}': {count} (Target: {min_commits})")
        else:
            make_daily_commits(target_path, min_commits=min_commits, push=push, repo_config=cfg)

def main():
    parser = argparse.ArgumentParser(description="Ensure minimum daily git commits script.")
    parser.add_argument("--repo-path", default=".", help="Path to target git repository (default: current dir)")
    parser.add_argument("--min-commits", type=int, default=10, help="Minimum daily commits target (default: 10)")
    parser.add_argument("--check-only", action="store_true", help="Check today's commit count without committing")
    parser.add_argument("--no-push", action="store_true", help="Commit locally without pushing to remote")
    parser.add_argument("--all-repos", action="store_true", help="Process all profile repositories from repositories.json")
    parser.add_argument("--sync-profile", action="store_true", help="Sync profile repositories from GitHub before running")
    parser.add_argument("--daemon", action="store_true", help="Run continuously checking every hour")
    parser.add_argument("--interval", type=int, default=3600, help="Daemon check interval in seconds (default: 3600)")
    
    args = parser.parse_args()
    
    if args.sync_profile and not args.all_repos:
        args.all_repos = True

    if args.all_repos:
        if args.daemon:
            print(f"Starting Multi-Repo Daily Commit Bot Daemon (Target min: {args.min_commits}, Interval: {args.interval}s)...")
            try:
                while True:
                    process_all_profile_repos(CONFIG_FILE, args.min_commits, push=not args.no_push, check_only=args.check_only, sync=args.sync_profile)
                    print(f"\nSleeping for {args.interval} seconds...")
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nDaemon stopped.")
        else:
            process_all_profile_repos(CONFIG_FILE, args.min_commits, push=not args.no_push, check_only=args.check_only, sync=args.sync_profile)
        return

    if args.check_only:
        count, _ = count_commits_today(args.repo_path)
        print(f"Commits made today in '{args.repo_path}': {count} (Minimum goal: {args.min_commits})")
        return
        
    if args.daemon:
        print(f"Starting Daily Commit Bot Daemon (Target min: {args.min_commits}, Interval: {args.interval}s)...")
        try:
            while True:
                make_daily_commits(args.repo_path, args.min_commits, push=not args.no_push)
                print(f"Sleeping for {args.interval} seconds...")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nDaemon stopped.")
    else:
        make_daily_commits(args.repo_path, args.min_commits, push=not args.no_push)

if __name__ == "__main__":
    main()
