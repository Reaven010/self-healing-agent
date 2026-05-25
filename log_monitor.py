import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from crew_workflow import run_healing_pipeline
from notifier import send_notification

LOG_FILE = os.getenv("TARGET_LOG_FILE", "app.log")

class LogHandler(FileSystemEventHandler):
    def __init__(self, filename):
        self.filename = filename
        self.last_pos = 0
        
        # Ensure file exists
        if not os.path.exists(self.filename):
            with open(self.filename, 'w') as f:
                f.write("")
        
        # Get initial file size
        self.last_pos = os.path.getsize(self.filename)

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(self.filename):
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
                print(f"New log entries detected:\n{content.strip()}")
                if "Error" in content or "Exception" in content:
                    print("Error detected! Triggering self-healing pipeline...")
                    self.trigger_pipeline(content)
        except Exception as e:
            print(f"Error reading new lines from log file: {e}")

    def trigger_pipeline(self, error_content):
        try:
            print("--- Starting CrewAI Agents ---")
            result = run_healing_pipeline(error_content)
            print("--- CrewAI Agents Finished ---")
            
            message = f"Self-Healing Pipeline completed.\n\nError:\n{error_content}\n\nAgent Output:\n{result}"
            send_notification("Self-Healing Pipeline Success", message)
        except Exception as e:
            err_msg = f"Self-Healing Pipeline failed: {str(e)}"
            print(err_msg)
            send_notification("Self-Healing Pipeline Failure", err_msg)

def start_monitor():
    # Watch the directory containing the target log file
    log_dir = os.path.dirname(os.path.abspath(LOG_FILE))
    if not log_dir or not os.path.exists(log_dir):
        log_dir = "."

    event_handler = LogHandler(LOG_FILE)
    observer = Observer()
    observer.schedule(event_handler, path=log_dir, recursive=False)
    
    print(f"Starting log monitor on {LOG_FILE} (watching folder: {log_dir})...")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_monitor()
