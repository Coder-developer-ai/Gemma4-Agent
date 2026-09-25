
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

import requests
import yaml


SUBMISSION_DIR = Path(__file__).resolve().parent
OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "gemma4:e2b"

MAX_FILE_SIZE = 200_000
MAX_TOOL_OUTPUT = 20_000
MAX_STEPS = 20



def read_text_file(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return f"[File too large: {path}]"

        return path.read_text(encoding="utf-8", errors="replace")

    except Exception as e:
        return f"[Error reading {path}: {e}]"


def safe_path(workspace: Path, relative_path: str) -> Path:
    """
    Resolve a path while preventing access outside the workspace.
    """

    if not relative_path:
        relative_path = "."

    candidate = (workspace / relative_path).resolve()
    workspace = workspace.resolve()

    try:
        candidate.relative_to(workspace)
    except ValueError:
        raise ValueError(
            f"Path '{relative_path}' is outside the workspace."
        )

    return candidate


def truncate_output(value) -> str:
    text = str(value)

    if len(text) > MAX_TOOL_OUTPUT:
        return text[:MAX_TOOL_OUTPUT] + "\n...[output truncated]"

    return text


def load_submission_context() -> str:
    sections = []



    prompts_dir = SUBMISSION_DIR / "prompts"

    if prompts_dir.exists():
        for path in sorted(prompts_dir.glob("*.md")):
            content = read_text_file(path)

            sections.append(
                f"\n===== PROMPT: {path.relative_to(SUBMISSION_DIR)} =====\n"
                f"{content}"
            )


    skills_dir = SUBMISSION_DIR / "skills"

    if skills_dir.exists():
        for path in sorted(skills_dir.rglob("*.md")):
            content = read_text_file(path)

            sections.append(
                f"\n===== SKILL: {path.relative_to(SUBMISSION_DIR)} =====\n"
                f"{content}"
            )

   

    agents_dir = SUBMISSION_DIR / "sub_agents"

    if agents_dir.exists():
        for path in sorted(agents_dir.glob("*.yaml")):
            content = read_text_file(path)

            sections.append(
                f"\n===== SUB-AGENT: {path.relative_to(SUBMISSION_DIR)} =====\n"
                f"{content}"
            )

    return "\n".join(sections)




def list_files(workspace: Path, path: str = "."):
    target = safe_path(workspace, path)

    if not target.exists():
        return f"Path does not exist: {path}"

    if not target.is_dir():
        return f"Not a directory: {path}"

    lines = []

    for item in sorted(target.rglob("*")):

        # Ignore Python cache directories
        if "__pycache__" in item.parts or ".git" in item.parts:
            continue

        try:
            relative = item.relative_to(workspace)

            if item.is_dir():
                lines.append(f"[DIR]  {relative}")
            else:
                lines.append(f"[FILE] {relative}")

        except Exception:
            continue

    if not lines:
        return "[Workspace is empty]"

    return "\n".join(lines)


def read_file(workspace: Path, path: str):
    target = safe_path(workspace, path)

    if not target.exists():
        return f"File does not exist: {path}"

    if not target.is_file():
        return f"Not a file: {path}"

    return read_text_file(target)


def search_files(
    workspace: Path,
    query: str,
    path: str = ".",
):
    root = safe_path(workspace, path)

    if not root.exists():
        return f"Path does not exist: {path}"

    results = []

    for file in root.rglob("*"):

        if not file.is_file():
            continue

        if "__pycache__" in file.parts:
            continue

        try:
            if file.stat().st_size > MAX_FILE_SIZE:
                continue

            content = file.read_text(
                encoding="utf-8",
                errors="replace",
            )

            if query.lower() in content.lower():
                relative = file.relative_to(workspace)
                results.append(str(relative))

        except Exception:
            continue

    if not results:
        return f"No files found containing: {query}"

    return "\n".join(results)


def write_file(
    workspace: Path,
    path: str,
    content: str,
):
    target = safe_path(workspace, path)

    if len(content.encode("utf-8")) > MAX_FILE_SIZE:
        return "ERROR: File is too large."

    target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(
        content,
        encoding="utf-8",
    )

    return f"Successfully wrote file: {path}"


def run_python(
    workspace: Path,
    script: str,
):
    try:
        result = subprocess.run(
            ["python", script],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = (
            f"Return code: {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

        return truncate_output(output)

    except subprocess.TimeoutExpired:
        return "ERROR: Python execution timed out."

    except Exception as e:
        return f"ERROR running Python: {e}"


def run_command(
    workspace: Path,
    command: str,
):
    """
    Execute a command inside the workspace.

    Some destructive commands are blocked.
    """

    blocked = [
        "format",
        "diskpart",
        "shutdown",
        "restart-computer",
        "remove-item",
        "del /s",
        "rmdir /s",
        "rd /s",
        "reg delete",
        "cipher /w",
    ]

    command_lower = command.lower()

    for forbidden in blocked:
        if forbidden in command_lower:
            return f"BLOCKED dangerous command: {forbidden}"

    try:
        result = subprocess.run(
            command,
            cwd=str(workspace),
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = (
            f"Return code: {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

        return truncate_output(output)

    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out."

    except Exception as e:
        return f"ERROR running command: {e}"


def run_tests(workspace: Path):
    """
    Run the project's test suite.
    Prefer pytest, then fall back to unittest.
    """

    # --------------------------------------------------------
    # pytest
    # --------------------------------------------------------

    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "-q"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=180,
        )

        output = (
            f"TEST COMMAND: python -m pytest -q\n"
            f"RETURN CODE: {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

        # pytest exists, so return its actual result,
        # including failures.
        if "No module named pytest" not in (
            result.stderr + result.stdout
        ):
            return truncate_output(output)

    except subprocess.TimeoutExpired:
        return "TEST RESULT: pytest timed out."

    except Exception as e:
        return f"pytest execution error: {e}"

    # --------------------------------------------------------
    # unittest fallback
    # --------------------------------------------------------

    try:
        result = subprocess.run(
            [
                "python",
                "-m",
                "unittest",
                "discover",
            ],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=180,
        )

        output = (
            f"TEST COMMAND: python -m unittest discover\n"
            f"RETURN CODE: {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

        return truncate_output(output)

    except subprocess.TimeoutExpired:
        return "TEST RESULT: unittest timed out."

    except Exception as e:
        return f"unittest execution error: {e}"


def git_status(workspace: Path):
    return run_command(workspace, "git status --short")


def git_diff(workspace: Path):
    return run_command(workspace, "git diff")



TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "search_files": search_files,
    "write_file": write_file,
    "run_python": run_python,
    "run_command": run_command,
    "run_tests": run_tests,
    "git_status": git_status,
    "git_diff": git_diff,
}


TOOL_DOCUMENTATION = """
AVAILABLE TOOLS

1. list_files
Purpose:
Inspect the repository structure.

Arguments:
{
  "path": "."
}


2. read_file
Purpose:
Read the actual contents of a file.

Arguments:
{
  "path": "relative/path/to/file"
}


3. search_files
Purpose:
Search repository files for text.

Arguments:
{
  "query": "text to search",
  "path": "."
}


4. write_file
Purpose:
Create or replace a file.

Arguments:
{
  "path": "relative/path/to/file",
  "content": "complete file contents"
}

IMPORTANT:
You MUST read a file before modifying an existing file.


5. run_python
Purpose:
Run a Python script inside the workspace.

Arguments:
{
  "script": "script.py"
}


6. run_command
Purpose:
Run a shell command inside the workspace.

Arguments:
{
  "command": "command"
}


7. run_tests
Purpose:
Run the complete project test suite.

Arguments:
{}


8. git_status
Purpose:
Show changed files.

Arguments:
{}


9. git_diff
Purpose:
Show the actual changes.

Arguments:
{}


TOOL-CALL FORMAT

When you need a tool, output ONLY valid JSON:

{
  "tool": "tool_name",
  "arguments": {
    "argument": "value"
  }
}

Do not use Markdown fences.

Do not explain the tool call.

Do not invent paths.

Only use paths that were returned by list_files or discovered from actual repository files.

When the requested task requires modifying code, you MUST actually call write_file.

When the requested task requires testing, you MUST actually call run_tests.

Never claim that a file was modified unless write_file successfully executed.

Never claim that tests passed unless run_tests successfully executed and its result shows success.
"""


def execute_tool(
    workspace: Path,
    tool_name: str,
    arguments: dict,
):
    if tool_name not in TOOLS:
        return f"ERROR: Unknown tool '{tool_name}'."

    try:
        tool = TOOLS[tool_name]

        if tool_name == "list_files":
            return tool(
                workspace,
                arguments.get("path", "."),
            )

        if tool_name == "read_file":
            return tool(
                workspace,
                arguments["path"],
            )

        if tool_name == "search_files":
            return tool(
                workspace,
                arguments["query"],
                arguments.get("path", "."),
            )

        if tool_name == "write_file":
            return tool(
                workspace,
                arguments["path"],
                arguments["content"],
            )

        if tool_name == "run_python":
            return tool(
                workspace,
                arguments["script"],
            )

        if tool_name == "run_command":
            return tool(
                workspace,
                arguments["command"],
            )

        if tool_name == "run_tests":
            return tool(workspace)

        if tool_name == "git_status":
            return tool(workspace)

        if tool_name == "git_diff":
            return tool(workspace)

        return "ERROR: Tool dispatch failed."

    except KeyError as e:
        return f"ERROR: Missing required argument: {e}"

    except Exception as e:
        return f"ERROR executing {tool_name}: {e}"



def ollama_chat(
    model: str,
    messages: list,
):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
        },
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=300,
    )

    response.raise_for_status()

    data = response.json()

    return data["message"]["content"]




def extract_json(text: str):
    """
    Extract JSON even if the model accidentally wraps it in
    Markdown fences or surrounding prose.
    """

    text = text.strip()

    # Direct JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # Markdown JSON block
    fenced = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass

    # Find first JSON object
    start = text.find("{")

    if start >= 0:
        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(text)):
            char = text[index]

            if escaped:
                escaped = False
                continue

            if char == "\\" and in_string:
                escaped = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1

            elif char == "}":
                depth -= 1

                if depth == 0:
                    candidate = text[start:index + 1]

                    try:
                        return json.loads(candidate)
                    except Exception:
                        break

    return None


def task_requires_modification(prompt: str) -> bool:
    keywords = [
        "implement",
        "modify",
        "change",
        "edit",
        "fix",
        "improve",
        "refactor",
        "add",
        "remove",
        "update",
        "create",
        "write",
    ]

    text = prompt.lower()

    return any(keyword in text for keyword in keywords)


def task_requires_tests(prompt: str) -> bool:
    text = prompt.lower()

    return any(
        keyword in text
        for keyword in [
            "test",
            "tests",
            "test suite",
            "pytest",
            "unittest",
        ]
    )


def run_agent(
    model: str,
    workspace: Path,
    user_prompt: str,
):
    context = load_submission_context()

    modification_required = task_requires_modification(
        user_prompt
    )

    tests_required = task_requires_tests(
        user_prompt
    )

    # Track actual operations.
    did_write = False
    did_test = False
    successful_writes = []
    test_results = []

    system_prompt = f"""
You are Gemma Local Agent, an autonomous software engineering agent.

You are operating inside this workspace:

{workspace}

You have access to the repository through tools.

{TOOL_DOCUMENTATION}

============================================================
CRITICAL EXECUTION RULES
============================================================

You must actually perform requested actions.

NEVER claim a file was changed unless write_file actually
executed successfully.

NEVER claim tests were run unless run_tests actually executed.

NEVER invent a file path.

For example, if list_files reports:

tests/test_todo_service.py

you MUST use exactly:

tests/test_todo_service.py

Do NOT invent:

tests/services/todo_service.py

Before modifying an existing file:

1. Find the exact path.
2. Read the file.
3. Understand the relevant code.
4. Modify it with write_file.

For a modification task, do not stop after explaining what
you intend to do.

Continue using tools until the requested work is complete.

For a task requiring tests:

1. Make the change.
2. Call run_tests.
3. Inspect the result.
4. If tests fail, investigate the failure.
5. Modify the code if necessary.
6. Run the tests again.
7. Only then provide the final report.

Your final report must distinguish between:

- files actually changed
- tests actually executed
- actual test results

Never fabricate any of these.

============================================================
SUBMISSION CONTEXT
============================================================

{context}
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    for step in range(1, MAX_STEPS + 1):

        print(f"\n[Agent step {step}]")

        try:
            response = ollama_chat(
                model,
                messages,
            )

        except Exception as e:
            print(f"\n[Ollama error] {e}")
            return

        print(response)

        parsed = extract_json(response)

     

        if isinstance(parsed, dict) and parsed.get("tool"):

            tool_name = parsed.get("tool")
            arguments = parsed.get("arguments", {})

            if not isinstance(arguments, dict):
                arguments = {}

            print(f"\n[Tool] {tool_name}")

            result = execute_tool(
                workspace,
                tool_name,
                arguments,
            )

            print("\n[Tool result]")
            print(result)


            if tool_name == "write_file":
                if result.startswith("Successfully wrote file:"):
                    did_write = True

                    path = arguments.get("path")

                    if path:
                        successful_writes.append(path)

          

            if tool_name == "run_tests":
                did_test = True
                test_results.append(result)

            messages.append(
                {
                    "role": "assistant",
                    "content": response,
                }
            )

            messages.append(
                {
                    "role": "user",
                    "content": (
                        "TOOL RESULT:\n"
                        f"{result}\n\n"
                        "Continue the task. "
                        "Do not give a final answer yet if "
                        "required actions remain."
                    ),
                }
            )

            continue



        # Modification required but no actual write happened.
        if modification_required and not did_write:

            print(
                "\n[Agent guard] "
                "The model attempted to finish without "
                "modifying a file. Continuing..."
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": response,
                }
            )

            messages.append(
                {
                    "role": "user",
                    "content": (
                        "STOP. You have NOT completed the task.\n\n"
                        "You have not successfully called write_file.\n"
                        "Do not provide a final report.\n\n"
                        "Continue inspecting the repository, "
                        "identify the genuine improvement, "
                        "and actually modify the correct file "
                        "using write_file.\n\n"
                        "Use exact paths from list_files/read_file."
                    ),
                }
            )

            continue

        # Tests required but not executed.
        if tests_required and not did_test:

            print(
                "\n[Agent guard] "
                "The model attempted to finish without "
                "running tests. Continuing..."
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": response,
                }
            )

            messages.append(
                {
                    "role": "user",
                    "content": (
                        "STOP. You have NOT completed the task.\n\n"
                        "You have not successfully called run_tests.\n"
                        "Do not claim test results.\n\n"
                        "Run the complete test suite now using "
                        "the run_tests tool.\n\n"
                        "If tests fail, inspect the failure, "
                        "fix the problem with write_file, "
                        "and run the tests again."
                    ),
                }
            )

            continue



        print("FINAL REPORT")


        print(response)

        if successful_writes:
            print("\nActual files modified:")
            for path in successful_writes:
                print(f"  - {path}")

        if did_test:
            print("\nTests were actually executed.")
        elif tests_required:
            print("\nWARNING: Tests were not executed.")

        return



   
    print("AGENT STOPPED")

    print(
        f"Maximum tool steps ({MAX_STEPS}) reached."
    )

    if successful_writes:
        print("\nFiles actually modified:")
        for path in successful_writes:
            print(f"  - {path}")

    if did_test:
        print("\nTests were executed.")
    else:
        print("\nTests were NOT executed.")



def main():
    parser = argparse.ArgumentParser(
        description="Gemma Local Agent"
    )

    parser.add_argument(
        "--model",
        default=os.environ.get(
            "OLLAMA_MODEL",
            DEFAULT_MODEL,
        ),
        help="Ollama model name",
    )

    parser.add_argument(
        "--workspace",
        default=".",
        help="Repository workspace",
    )

    parser.add_argument(
        "--prompt",
        default=None,
        help="One-shot task prompt",
    )

    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()

    if not workspace.exists():
        print(
            f"ERROR: Workspace does not exist:\n"
            f"{workspace}"
        )
        return

    if not workspace.is_dir():
        print(
            f"ERROR: Workspace is not a directory:\n"
            f"{workspace}"
        )
        return

    print("GEMMA LOCAL AGENT")

    print(f"Model:     {args.model}")
    print(f"Workspace: {workspace}")
  


    if args.prompt:
        run_agent(
            args.model,
            workspace,
            args.prompt,
        )
        return


    print("Interactive mode.")
    print("Type 'exit' or 'quit' to stop.")

    while True:

        try:
            prompt = input("\nYou: ").strip()

        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not prompt:
            continue

        if prompt.lower() in {
            "exit",
            "quit",
        }:
            break

        run_agent(
            args.model,
            workspace,
            prompt,
        )


if __name__ == "__main__":
    main()
