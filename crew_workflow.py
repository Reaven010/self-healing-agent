import os
from crewai import Agent, Task, Crew, Process, LLM
from dotenv import load_dotenv

from tools import run_pytest, git_commit_tool, read_file_tool, write_file_tool

load_dotenv()

# Initialize LM Studio LLM natively using CrewAI's LLM class
api_base = os.getenv("OPENAI_API_BASE", "http://localhost:1234/v1")
if not api_base.endswith("/v1") and not api_base.endswith("/v1/"):
    api_base = api_base.rstrip("/") + "/v1"

llm = LLM(
    model="openai/" + os.getenv("OPENAI_MODEL_NAME", "local-model"),
    base_url=api_base,
    api_key=os.getenv("OPENAI_API_KEY", "lm-studio"),
    temperature=0.1
)

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

def create_tasks(error_log, agents):
    rc_agent, cf_agent, test_agent, git_agent = agents

    rc_task = Task(
        description=f"Analyze the following error log and determine the root cause:\n{error_log}\nRead the relevant files to understand the bug.",
        expected_output="A detailed explanation of the root cause and exactly which file/line needs to be fixed.",
        agent=rc_agent
    )

    cf_task = Task(
        description="Based on the root cause analysis, fix the code. Use the Read File Tool to read the broken file, and Write File Tool to rewrite it with the fix.",
        expected_output="Confirmation that the file has been successfully written with the bug fix.",
        agent=cf_agent
    )

    test_task = Task(
        description="Run pytest using the Run Pytest Tool to verify the fix works. If it fails, report the error. If it passes, confirm success.",
        expected_output="The output of the test execution, confirming tests passed.",
        agent=test_agent
    )

    git_task = Task(
        description="If the tests passed, use the Git Commit Tool to commit the changes. Write a descriptive commit message explaining what bug was fixed.",
        expected_output="Confirmation that the git commit was successful.",
        agent=git_agent
    )

    return [rc_task, cf_task, test_task, git_task]

def run_healing_pipeline(error_log):
    agents = create_crew()
    tasks = create_tasks(error_log, agents)

    crew = Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True
    )

    result = crew.kickoff()
    return result
