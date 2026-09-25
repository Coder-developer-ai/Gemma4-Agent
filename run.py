
import argparse
import json
import os
import subprocess
from pathlib import Path

import requests
import yaml




SUBMISSION_DIR = Path(__file__).resolve().parent

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "gemma4:e2b"

MAX_FILE_SIZE = 200_000
MAX_TOOL_OUTPUT = 20_000




def read_text_file(path):
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return "[FILE TOO LARGE TO READ]"

        return path.read_text(encoding="utf-8", errors="replace")

    except Exception as e:
        return f"[ERROR READING FILE: {e}]"


def safe_path(workspace, relative_path):
    """
    Prevent the model from escaping the selected workspace.
    """

    workspace = workspace.resolve()
    target = (workspace / relative_path).resolve()

    try:
        target.relative_to(workspace)
    except ValueError:
        raise ValueError("Path escapes the workspace.")

    return target



def load_submission_context():

    parts = []

    # Main system prompt
    system_file = SUBMISSION_DIR / "prompts" / "system.md"

    if system_file.exists():
        parts.append(
            "=== SYSTEM PROMPT ===\n"
            + read_text_file(system_file)
        )

    # Other prompts
    prompts_dir = SUBMISSION_DIR / "prompts"

    if prompts_dir.exists():

        for file in sorted(prompts_dir.glob("*.md")):

            if file.name == "system.md":
                continue

            parts.append(
                f"=== PROMPT: {file.name} ===\n"
                + read_text_file(file)
            )

    # Skills
    skills_dir = SUBMISSION_DIR / "skills"

    if skills_dir.exists():

        for skill_file in sorted(skills_dir.rglob("SKILL.md")):

            parts.append(
                f"=== SKILL: {skill_file.parent.name} ===\n"
                + read_text_file(skill_file)
            )

            resources = skill_file.parent / "resources"

            if resources.exists():

                for resource in sorted(resources.rglob("*")):

                    if resource.is_file():

                        parts.append(
                            f"=== SKILL RESOURCE: {resource.name} ===\n"
                            + read_text_file(resource)
                        )

    # Sub-agents
    agents_dir = SUBMISSION_DIR / "sub_agents"

    if agents_dir.exists():

        for agent_file in sorted(agents_dir.glob("*.yaml")):

            parts.append(
                f"=== SUB-AGENT: {agent_file.name} ===\n"
                + read_text_file(agent_file)
            )

    return "\n\n".join(parts)




def list_files(workspace, path="."):

    directory = safe_path(workspace, path)

    if not directory.is_dir():
        return f"Not a directory: {path}"

    results = []

    for item in sorted(directory.rglob("*")):

        if ".git" in item.parts:
            continue

        try:
            relative = item.relative_to(workspace)

            if item.is_dir():
                results.append(f"[DIR]  {relative}")
            else:
                results.append(f"[FILE] {relative}")

        except Exception:
            pass

    return "\n".join(results[:5000])


def read_file(workspace, path):

    target = safe_path(workspace, path)

    if not target.exists():
        return f"File does not exist: {path}"

    if not target.is_file():
        return f"Not a file: {path}"

    return read_text_file(target)


def search_files(workspace, query):

    results = []

    for file in workspace.rglob("*"):

        if not file.is_file():
            continue

        if ".git" in file.parts:
            continue

        if file.stat().st_size > MAX_FILE_SIZE:
            continue

        try:
            text = file.read_text(
                encoding="utf-8",
                errors="ignore"
            )

            if query.lower() in text.lower():

                results.append(
                    str(file.relative_to(workspace))
                )

        except Exception:
            continue

        if len(results) >= 200:
            break

    if not results:
        return "No matches found."

    return "\n".join(results)


def write_file(workspace, path, content):

    target = safe_path(workspace, path)

    target.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    target.write_text(
        content,
        encoding="utf-8"
    )

    return f"Successfully wrote: {path}"


def run_python(workspace, code):

    try:

        result = subprocess.run(
            ["python", "-c", code],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60
        )

        return (
            f"EXIT CODE: {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    except subprocess.TimeoutExpired:
        return "Python execution timed out after 60 seconds."

    except Exception as e:
        return f"Python execution error: {e}"


def run_command(workspace, command):

    # Basic dangerous-command protection.
    blocked = [
        "format ",
        "diskpart",
        "shutdown",
        "restart-computer",
        "remove-item",
        "del /s",
        "rmdir /s",
        "rd /s",
        "reg delete",
        "cipher /w"
    ]

    lowered = command.lower()

    for item in blocked:

        if item in lowered:
            return f"Command blocked for safety: {item}"

    try:

        result = subprocess.run(
            command,
            cwd=workspace,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )

        return (
            f"EXIT CODE: {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    except subprocess.TimeoutExpired:
        return "Command timed out after 120 seconds."

    except Exception as e:
        return f"Command execution error: {e}"


def git_status(workspace):

    return run_command(
        workspace,
        "git status --short"
    )


def git_diff(workspace):

    return run_command(
        workspace,
        "git diff"
    )


def run_tests(workspace):

    commands = [
        "pytest -q",
        "python -m unittest discover"
    ]

    for command in commands:

        result = run_command(
            workspace,
            command
        )

        if "No module named pytest" not in result:
            return result

    return "No supported test runner was available."




def execute_tool(workspace, name, arguments):

    try:

        if name == "list_files":
            return list_files(
                workspace,
                arguments.get("path", ".")
            )

        if name == "read_file":
            return read_file(
                workspace,
                arguments["path"]
            )

        if name == "search_files":
            return search_files(
                workspace,
                arguments["query"]
            )

        if name == "write_file":
            return write_file(
                workspace,
                arguments["path"],
                arguments["content"]
            )

        if name == "run_python":
            return run_python(
                workspace,
                arguments["code"]
            )

        if name == "run_command":
            return run_command(
                workspace,
                arguments["command"]
            )

        if name == "run_tests":
            return run_tests(workspace)

        if name == "git_status":
            return git_status(workspace)

        if name == "git_diff":
            return git_diff(workspace)

        return f"Unknown tool: {name}"

    except KeyError as e:
        return f"Missing required argument: {e}"

    except Exception as e:
        return f"Tool error: {e}"


TOOLS = [

    {
        "name": "list_files",
        "description": "List files and directories in the workspace.",
        "arguments": {
            "path": "relative directory path"
        }
    },

    {
        "name": "read_file",
        "description": "Read a text file from the workspace.",
        "arguments": {
            "path": "relative file path"
        }
    },

    {
        "name": "search_files",
        "description": "Search text across workspace files.",
        "arguments": {
            "query": "text to search for"
        }
    },

    {
        "name": "write_file",
        "description": "Create or replace a text file.",
        "arguments": {
            "path": "relative file path",
            "content": "complete file contents"
        }
    },

    {
        "name": "run_python",
        "description": "Execute a short Python program inside the workspace.",
        "arguments": {
            "code": "Python code"
        }
    },

    {
        "name": "run_command",
        "description": "Run a terminal command inside the workspace.",
        "arguments": {
            "command": "terminal command"
        }
    },

    {
        "name": "run_tests",
        "description": "Run available Python tests.",
        "arguments": {}
    },

    {
        "name": "git_status",
        "description": "Show Git working-tree status.",
        "arguments": {}
    },

    {
        "name": "git_diff",
        "description": "Show current Git changes.",
        "arguments": {}
    }
]


def tool_documentation():

    return json.dumps(
        TOOLS,
        indent=2
    )


# ============================================================
# OLLAMA
# ============================================================

def ollama_chat(model, messages):

    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=600
    )

    response.raise_for_status()

    data = response.json()

    return data["message"]["content"]




def run_agent(model, workspace, user_prompt):

    context = load_submission_context()

    system_prompt = f"""
You are an autonomous software engineering agent.

You are running locally through Ollama using model: {model}

Your workspace is:

{workspace}

You have access to these tools:

{tool_documentation()}

You also have access to the submission's prompts, skills,
skill resources, and sub-agent definitions below.

{context}

============================================================
TOOL CALL FORMAT
============================================================

When you need a tool, output ONLY this JSON object:

{{
  "tool": "tool_name",
  "arguments": {{
    "argument": "value"
  }}
}}

Examples:

{{"tool":"list_files","arguments":{{"path":"."}}}}

{{"tool":"read_file","arguments":{{"path":"main.py"}}}}

{{"tool":"search_files","arguments":{{"query":"TODO"}}}}

{{"tool":"run_tests","arguments":{{}}}}

After receiving a TOOL RESULT, continue working.

Do not invent tool results.

Use tools when they provide useful evidence.

For code changes:
1. Inspect the repository first.
2. Understand the relevant code.
3. Make the smallest appropriate change.
4. Run tests or validation.
5. Inspect the result.
6. Fix problems if necessary.
7. Give the user a concise summary.

Do not expose private chain-of-thought.
Provide concise reasoning summaries instead.

============================================================
USER TASK
============================================================

{user_prompt}
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    max_steps = 15

    for step in range(max_steps):

        response = ollama_chat(
            model,
            messages
        )

        print(f"\n[Agent step {step + 1}]")
        print(response)

        # Try to interpret tool request
        cleaned = response.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "")
            cleaned = cleaned.replace("```", "")
            cleaned = cleaned.strip()

        try:

            request = json.loads(cleaned)

        except json.JSONDecodeError:

            # Normal final response
            return response

        if not isinstance(request, dict):
            return response

        tool_name = request.get("tool")

        if not tool_name:
            return response

        arguments = request.get(
            "arguments",
            {}
        )

        print(
            f"\n[Tool] {tool_name}"
        )

        result = execute_tool(
            workspace,
            tool_name,
            arguments
        )

        if len(result) > MAX_TOOL_OUTPUT:
            result = result[:MAX_TOOL_OUTPUT] + \
                     "\n...[OUTPUT TRUNCATED]..."

        print(
            "\n[Tool result]\n"
            + result
        )

        messages.append(
            {
                "role": "assistant",
                "content": response
            }
        )

        messages.append(
            {
                "role": "user",
                "content": (
                    "TOOL RESULT\n"
                    f"Tool: {tool_name}\n\n"
                    f"{result}\n\n"
                    "Continue the task."
                )
            }
        )

    return "Agent reached the maximum number of tool steps."


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Gemma local tool-using agent"
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL
    )

    parser.add_argument(
        "--workspace",
        default=".",
        help="Repository/workspace the agent can access."
    )

    parser.add_argument(
        "--prompt",
        help="Single task for the agent."
    )

    args = parser.parse_args()

    workspace = Path(
        args.workspace
    ).resolve()

    if not workspace.exists():
        print(f"Workspace does not exist: {workspace}")
        raise SystemExit(1)

    print("=" * 70)
    print("GEMMA LOCAL AGENT")
    print("=" * 70)
    print(f"Model:     {args.model}")
    print(f"Workspace: {workspace}")
    print("=" * 70)

    if args.prompt:

        run_agent(
            args.model,
            workspace,
            args.prompt
        )

        return

    print("\nInteractive mode.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:

        try:
            prompt = input("You: ").strip()

        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not prompt:
            continue

        if prompt.lower() in {
            "exit",
            "quit"
        }:
            break

        try:

            run_agent(
                args.model,
                workspace,
                prompt
            )

        except Exception as e:

            print(
                f"\nERROR: {e}\n"
            )


if __name__ == "__main__":
    main()

