import os
import sys

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


from crewai import Agent, Task, Crew, Process, LLM
from dotenv import load_dotenv


from tools import run_pytest, git_commit_tool, read_file_tool, write_file_tool

load_dotenv()

# Initialize LLM (supports local LM Studio/Ollama AND online Cloud APIs like Gemini, OpenAI, Groq)
model_name = os.getenv("OPENAI_MODEL_NAME", "gemini/gemini-1.5-flash")
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY", "lm-studio")
api_base = os.getenv("OPENAI_API_BASE", "").strip()

llm_kwargs = {
    "api_key": api_key,
    "temperature": 0.1
}

# Format model string for CrewAI / LiteLLM
if "/" in model_name or model_name.startswith("gpt-") or model_name.startswith("claude-"):
    llm_kwargs["model"] = model_name
elif model_name.startswith("gemini"):
    llm_kwargs["model"] = f"gemini/{model_name}" if not model_name.startswith("gemini/") else model_name
    llm_kwargs["use_native"] = False
else:
    llm_kwargs["model"] = f"openai/{model_name}"

if api_base:
    if not api_base.endswith("/v1") and not api_base.endswith("/v1/"):
        api_base = api_base.rstrip("/") + "/v1"
    llm_kwargs["base_url"] = api_base

llm = LLM(**llm_kwargs)




def create_crew():
    # 1. Root Cause Agent
    root_cause_agent = Agent(
        role="Root Cause Analyst",
        goal="Analyze the error log and identify the exact root cause of the failure in the code.",
        backstory="You are an expert debugger. Given an error trace, you can find exactly why the code failed by reading the relevant source files.",
        verbose=True,
        allow_delegation=False,
        tools=[read_file_tool],
        llm=llm
    )

    # 2. Code Fix Agent
    code_fix_agent = Agent(
        role="Senior Software Engineer",
        goal="Fix the bug identified by the Root Cause Analyst and write the corrected code to the file.",
        backstory="You are a 10x engineer who writes flawless code. You receive bug reports and apply fixes directly to the source code.",
        verbose=True,
        allow_delegation=False,
        tools=[read_file_tool, write_file_tool],
        llm=llm
    )

    # 3. Test Agent
    test_agent = Agent(
        role="QA Automation Engineer",
        goal="Run the test suite and verify if the applied code fix passes all tests.",
        backstory="You ensure software quality by running tests. If tests fail, you provide detailed output.",
        verbose=True,
        allow_delegation=False,
        tools=[run_pytest],
        llm=llm
    )

    # 4. Git Commit Agent
    git_commit_agent = Agent(
        role="Release Manager",
        goal="Commit the fixed code into the git repository with a clear message.",
        backstory="You are responsible for safely committing changes to version control once they are tested.",
        verbose=True,
        allow_delegation=False,
        tools=[git_commit_tool],
        llm=llm
    )

    return root_cause_agent, code_fix_agent, test_agent, git_commit_agent

def create_tasks(error_log, agents, repo_config):
    rc_agent, cf_agent, test_agent, git_agent = agents
    repo_name = repo_config.get("name", "Target Repository")
    repo_path = repo_config.get("repo_path", ".")
    is_remote = "server" in repo_config
    location_desc = f"remote server ({repo_config['server'].get('host')})" if is_remote else "local machine"

    rc_task = Task(
        description=f"Analyze the following error log and determine the root cause:\n{error_log}\n"
                    f"Read the relevant files to understand the bug. The repository is named '{repo_name}' "
                    f"and resides in '{repo_path}' on the {location_desc}.",
        expected_output="A detailed explanation of the root cause and exactly which file/line needs to be fixed.",
        agent=rc_agent
    )

    cf_task = Task(
        description=f"Based on the root cause analysis, fix the code in the repository '{repo_name}' residing at '{repo_path}' on the {location_desc}. "
                    f"Use the Read File Tool to read the broken file, and Write File Tool to rewrite it with the fix.",
        expected_output="Confirmation that the file has been successfully written with the bug fix.",
        agent=cf_agent
    )

    test_task = Task(
        description=f"Run pytest inside the target repository '{repo_name}' at '{repo_path}' on the {location_desc} "
                    f"using the Run Pytest Tool to verify the fix works. If it fails, report the error. If it passes, confirm success.",
        expected_output="The output of the test execution, confirming tests passed.",
        agent=test_agent
    )

    git_task = Task(
        description=f"If the tests passed, use the Git Commit Tool to commit the changes inside target repository '{repo_name}' "
                    f"at '{repo_path}' on the {location_desc}. Write a descriptive commit message explaining what bug was fixed.",
        expected_output="Confirmation that the git commit was successful.",
        agent=git_agent
    )

    return [rc_task, cf_task, test_task, git_task]

def run_healing_pipeline(error_log, repo_config):
    # Set the thread/execution-wide active repository configuration for tool binding
    from tools import set_active_repo, get_target_path
    set_active_repo(repo_config)

    try:
        agents = create_crew()
        tasks = create_tasks(error_log, agents, repo_config)

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()
        return result
    finally:
        local_path = get_target_path()
        if os.path.exists(local_path):
            repo_name = repo_config.get("name", "temp_repo").replace(" ", "_").lower()
            print(f"\n[{repo_name}] Deleting cloned repository directory at '{local_path}'...")
            import shutil
            import time
            # Try up to 5 times with a brief delay to release Windows file locks
            for i in range(5):
                try:
                    shutil.rmtree(local_path)
                    print(f"[{repo_name}] Repository successfully deleted.")
                    break
                except Exception as e:
                    if i == 4:
                        print(f"[{repo_name}] Warning: Failed to delete cloned repository directory: {e}")
                    else:
                        time.sleep(1)

