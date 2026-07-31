import sys
import argparse
import threading

# Automatic SQLite3 fallback shim for Linux environments missing native _sqlite3
try:
    import _sqlite3
except Exception:
    try:
        import pysqlite3
        sys.modules["sqlite3"] = sys.modules["pysqlite3"]
        sys.modules["_sqlite3"] = sys.modules["pysqlite3"]
    except Exception:
        pass


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from log_monitor import start_monitor
from daily_commit_bot import make_daily_commits, process_all_profile_repos
from repo_discovery import sync_repositories_config, CONFIG_FILE

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Self-Healing Pipeline with Profile-Wide Repository Monitoring & Commit Tracker")
    parser.add_argument("--sync-profile", action="store_true", help="Sync all GitHub profile repositories into repositories.json before starting")
    parser.add_argument("--enforce-daily-commits", action="store_true", help="Enforce minimum daily commits on startup")
    parser.add_argument("--all-repos", action="store_true", help="Apply daily commit enforcement across all profile repositories")
    parser.add_argument("--min-commits", type=int, default=10, help="Minimum daily commit count (default: 10)")
    args = parser.parse_args()

    print("Initializing Self-Healing Pipeline with Profile-Wide Repository Monitoring...")
    print("This pipeline uses CrewAI agents powered by your local LM Studio instance or Cloud LLM API.")

    if args.sync_profile:
        print("\n[GitHub Sync] Synchronizing profile repositories from GitHub...")
        sync_repositories_config()

    if args.enforce_daily_commits:
        if args.all_repos or args.sync_profile:
            print(f"\n[Daily Commit Bot] Verifying minimum {args.min_commits} daily commits across all profile repositories...")
            process_all_profile_repos(config_file=CONFIG_FILE, min_commits=args.min_commits, push=True)
        else:
            print(f"\n[Daily Commit Bot] Verifying minimum {args.min_commits} daily commits for target repository...")
            make_daily_commits(".", min_commits=args.min_commits, push=True)

    start_monitor(sync_profile=False)
