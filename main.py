from log_monitor import start_monitor

if __name__ == "__main__":
    print("Initializing Self-Healing Pipeline...")
    print("This pipeline uses CrewAI agents powered by your local LM Studio instance.")
    print("Ensure LM Studio is running and the API is available at http://localhost:1234/v1")
    start_monitor()
