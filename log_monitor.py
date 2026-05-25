import time
import os
import json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from crew_workflow import run_healing_pipeline
from notifier import send_notification

CONFIG_FILE = "repositories.json"

class LogHandler(FileSystemEventHandler):
    def __init__(self, repo_config):
        self.repo_config = repo_config
        self.filename = repo_config["log_file"]
        self.last_pos = 0
        
        # Ensure log file exists locally
        if not os.path.exists(self.filename):
            parent_dir = os.path.dirname(os.path.abspath(self.filename))
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            with open(self.filename, 'w', encoding='utf-8') as f:
                f.write("")
        
        # Get initial file size
        self.last_pos = os.path.getsize(self.filename)

    def on_modified(self, event):
        # Precise matching on the specific log file absolute path
        if not event.is_directory and os.path.abspath(event.src_path) == os.path.abspath(self.filename):
            self.read_new_lines()

    def read_new_lines(self):
        try:
            # If file size is smaller than our last position, it was truncated/overwritten. Reset pointer to 0.
            current_size = os.path.getsize(self.filename)
            if current_size < self.last_pos:
                self.last_pos = 0

            # Open with utf-8 and ignore/replace decoding errors to prevent crashes
            with open(self.filename, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(self.last_pos)
                new_lines = f.readlines()
                self.last_pos = f.tell()

            if new_lines:
                content = "".join(new_lines)
                print(f"\n[{self.repo_config['name']}] New log entries detected:\n{content.strip()}")
                if "Error" in content or "Exception" in content:
                    print(f"[{self.repo_config['name']}] Error detected! Triggering self-healing pipeline...")
                    self.trigger_pipeline(content)
        except Exception as e:
            print(f"[{self.repo_config['name']}] Error reading new lines from log file: {e}")

    def trigger_pipeline(self, error_content):
        try:
            print(f"\n--- Starting CrewAI Agents for repository: {self.repo_config['name']} ---")
            result = run_healing_pipeline(error_content, self.repo_config)
            print(f"--- CrewAI Agents Finished for repository: {self.repo_config['name']} ---\n")
            
            message = f"Self-Healing Pipeline completed for {self.repo_config['name']}.\n\nError:\n{error_content}\n\nAgent Output:\n{result}"
            send_notification(f"Self-Healing Pipeline Success - {self.repo_config['name']}", message)
        except Exception as e:
            err_msg = f"Self-Healing Pipeline failed for {self.repo_config['name']}: {str(e)}"
            print(err_msg)
            send_notification(f"Self-Healing Pipeline Failure - {self.repo_config['name']}", err_msg)

def start_monitor():
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Configuration file '{CONFIG_FILE}' not found. Please create it first.")
        return

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            repo_configs = json.load(f)
    except Exception as e:
        print(f"Error reading configuration file '{CONFIG_FILE}': {e}")
        return

    if not isinstance(repo_configs, list) or len(repo_configs) == 0:
        print(f"Error: '{CONFIG_FILE}' must be a non-empty list of repository configurations.")
        return

    observer = Observer()
    handlers = []
    
    print("Initializing multi-repository log monitor...")
    for config in repo_configs:
        log_file = config.get("log_file")
        name = config.get("name", "Unnamed Repo")
        if not log_file:
            print(f"Warning: Repository '{name}' is missing 'log_file' configuration. Skipping.")
            continue
            
        log_dir = os.path.dirname(os.path.abspath(log_file))
        if not log_dir or not os.path.exists(log_dir):
            log_dir = "."
            
        handler = LogHandler(config)
        handlers.append(handler)
        observer.schedule(handler, path=log_dir, recursive=False)
        print(f"Watching logs for '{name}' at '{log_file}' (folder: {log_dir})")

    print("\nStarting log monitor service... Press Ctrl+C to stop.")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping log monitor service...")
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_monitor()
