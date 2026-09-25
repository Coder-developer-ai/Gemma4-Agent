
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests


# ============================================================
# Configuration
# ============================================================

SUBMISSION_DIR = Path(__file__).resolve().parent
OLLAMA_URL = os.environ.get(
    "OLLAMA_URL",
    "http://localhost:11434/api/chat",
)
DEFAULT_MODEL = os.environ.get("GEMMA_MODEL", "gemma4:e2b")

MAX_FILE_SIZE = 300_000
MAX_TOOL_OUTPUT = 12_000
MAX_STEPS = 25


# ============================================================
# General helpers
# ============================================================

def truncate_output(value: Any, limit: int = MAX_TOOL_OUTPUT) -> str:
    text = str(value)

    if len(text) <= limit:
        return text

    return text[:limit] + "\n...[output truncated]..."


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def safe_path(workspace: Path, relative_path: str) -> Path:
    """
    Resolve a repository-relative path while preventing escape
    outside the selected workspace.
    """

    if not relative_path:
        raise ValueError("Path cannot be empty.")

    candidate = Path(relative_path)

    if candidate.is_absolute():
        raise ValueError("Absolute paths are not allowed.")

    resolved = (workspace / candidate).resolve()
    workspace_resolved = workspace.resolve()

    try:
        resolved.relative_to(workspace_resolved)
    except ValueError:
        raise ValueError("Path escapes the workspace.")

    return resolved


def load_optional(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""

    return read_text_file(path)


# ============================================================
# Submission context
# ============================================================

def load_submission_context() -> str:
    """
    Loads the local submission configuration so Gemma can use
    the same prompts/skills/sub-agent descriptions during local
    development.

    This does NOT execute Kaggle ADK skills. Kaggle executes the
    submitted agent through its own harness.
    """

    sections: list[str] = []

    prompt_files = [
        SUBMISSION_DIR / "prompts" / "system.md",
        SUBMISSION_DIR / "prompts" / "localization.md",
        SUBMISSION_DIR / "prompts" / "debugging.md",
    ]

    for path in prompt_files:
        content = load_optional(path)

        if content:
            sections.append(
                f"\n===== PROMPT: {path.relative_to(SUBMISSION_DIR)} =====\n"
                f"{content}"
            )

    skills_dir = SUBMISSION_DIR / "skills"

    if skills_dir.exists():
        for skill_file in sorted(skills_dir.rglob("SKILL.md")):
            content = load_optional(skill_file)

            if content:
                sections.append(
                    f"\n===== SKILL: "
                    f"{skill_file.relative_to(SUBMISSION_DIR)} =====\n"
                    f"{content}"
                )

            resource_dir = skill_file.parent / "resources"

            if resource_dir.exists():
                for resource in sorted(resource_dir.rglob("*")):
                    if resource.is_file() and resource.suffix.lower() in {
                        ".md",
                        ".txt",
                        ".yaml",
                        ".yml",
                        ".json",
                    }:
                        content = load_optional(resource)

                        if content:
                            sections.append(
                                f"\n===== SKILL RESOURCE: "
                                f"{resource.relative_to(SUBMISSION_DIR)} =====\n"
                                f"{content}"
                            )

    sub_agents_dir = SUBMISSION_DIR / "sub_agents"

    if sub_agents_dir.exists():
        for config in sorted(sub_agents_dir.glob("*.yaml")):
            content = load_optional(config)

            if content:
                sections.append(
                    f"\n===== SUB-AGENT: "
                    f"{config.relative_to(SUBMISSION_DIR)} =====\n"
                    f"{content}"
                )

    return "\n".join(sections)


# ============================================================
# Local tools
# ============================================================

def list_files(workspace: Path) -> str:
    """
    List repository files while excluding generated metadata.
    """

    results: list[str] = []

    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue

        relative = path.relative_to(workspace)

        # Ignore Git internals and Python caches.
        if ".git" in relative.parts:
            continue

        if "__pycache__" in relative.parts:
            continue

        if ".pytest_cache" in relative.parts:
            continue

        if ".mypy_cache" in relative.parts:
            continue

        if ".venv" in relative.parts:
            continue

        results.append(relative.as_posix())

        if len(results) >= 1000:
            break

    if not results:
        return "(No files found.)"

    return "\n".join(results)


def read_file(workspace: Path, filepath: str) -> str:
    path = safe_path(workspace, filepath)

    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {filepath}")

    if not path.is_file():
        raise ValueError(f"Not a file: {filepath}")

    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(
            f"File is larger than {MAX_FILE_SIZE} bytes. "
            f"Read a smaller file or inspect relevant sections."
        )

    return truncate_output(read_text_file(path))


def search_files(
    workspace: Path,
    query: str,
    file_pattern: str = "*",
) -> str:
    if not query:
        raise ValueError("Search query cannot be empty.")

    results: list[str] = []

    for path in sorted(workspace.rglob(file_pattern)):
        if not path.is_file():
            continue

        relative = path.relative_to(workspace)

        if ".git" in relative.parts:
            continue

        if "__pycache__" in relative.parts:
            continue

        if ".venv" in relative.parts:
            continue

        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue

            text = read_text_file(path)

            if query.lower() in text.lower():
                results.append(relative.as_posix())

        except OSError:
            continue

        if len(results) >= 100:
            break

    if not results:
        return "No matching files found."

    return "\n".join(results)


def write_file(
    workspace: Path,
    filepath: str,
    content: str,
) -> str:
    path = safe_path(workspace, filepath)

    if len(content.encode("utf-8")) > MAX_FILE_SIZE:
        raise ValueError(
            f"Content exceeds the {MAX_FILE_SIZE}-byte limit."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return f"Successfully wrote: {path.relative_to(workspace).as_posix()}"


def run_python(
    workspace: Path,
    filepath: str,
) -> str:
    path = safe_path(workspace, filepath)

    if not path.exists():
        raise FileNotFoundError(filepath)

    if path.suffix.lower() != ".py":
        raise ValueError("run_python requires a .py file.")

    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=120,
    )

    output = (
        f"returncode={result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    return truncate_output(output)


def run_command(
    workspace: Path,
    command: str,
) -> str:
    """
    Local-development command runner.

    Keep this deliberately restricted. The competition harness has
    its own run_command implementation.
    """

    if not command.strip():
        raise ValueError("Command cannot be empty.")

    lowered = command.lower()

    blocked_fragments = [
        "format c:",
        "diskpart",
        "shutdown",
        "restart-computer",
        "remove-item -recurse",
        "rmdir /s",
        "del /s /q",
    ]

    for fragment in blocked_fragments:
        if fragment in lowered:
            raise ValueError(
                "Command blocked by the local safety guard."
            )

    result = subprocess.run(
        command,
        cwd=str(workspace),
        shell=True,
        capture_output=True,
        text=True,
        timeout=180,
    )

    output = (
        f"returncode={result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    return truncate_output(output)


def run_tests(workspace: Path) -> str:
    """
    Run the complete pytest suite.

    The agent must use this tool before claiming that tests
    were executed.
    """

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=300,
    )

    output = (
        f"TEST_RETURN_CODE={result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    return truncate_output(output, 16_000)


def git_status(workspace: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=30,
    )

    return truncate_output(
        f"returncode={result.returncode}\n"
        f"{result.stdout}\n{result.stderr}"
    )


def git_diff(workspace: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "--"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=30,
    )

    return truncate_output(
        f"returncode={result.returncode}\n"
        f"{result.stdout}\n{result.stderr}",
        20_000,
    )


# ============================================================
# Tool dispatcher
# ============================================================

def execute_tool(
    workspace: Path,
    name: str,
    arguments: dict[str, Any],
) -> str:

    if name == "list_files":
        return list_files(workspace)

    if name == "read_file":
        return read_file(
            workspace,
            arguments["filepath"],
        )

    if name == "search_files":
        return search_files(
            workspace,
            arguments["query"],
            arguments.get("file_pattern", "*"),
        )

    if name == "write_file":
        return write_file(
            workspace,
            arguments["filepath"],
            arguments["content"],
        )

    if name == "run_python":
        return run_python(
            workspace,
            arguments["filepath"],
        )

    if name == "run_command":
        return run_command(
            workspace,
            arguments["command"],
        )

    if name == "run_tests":
        return run_tests(workspace)

    if name == "git_status":
        return git_status(workspace)

    if name == "git_diff":
        return git_diff(workspace)

    raise ValueError(f"Unknown tool: {name}")


# ============================================================
# Model protocol
# ============================================================

TOOL_DESCRIPTIONS = """
Available local-development tools:

1. list_files
   Arguments:
   {}

2. read_file
   Arguments:
   {"filepath": "relative/path.py"}

3. search_files
   Arguments:
   {"query": "text", "file_pattern": "*.py"}

4. write_file
   Arguments:
   {
     "filepath": "relative/path.py",
     "content": "complete file content"
   }

5. run_python
   Arguments:
   {"filepath": "relative/path.py"}

6. run_command
   Arguments:
   {"command": "command"}

7. run_tests
   Arguments:
   {}

8. git_status
   Arguments:
   {}

9. git_diff
   Arguments:
   {}

Tool calls MUST be returned as JSON:

{
  "tool": "tool_name",
  "arguments": {}
}

When the task is genuinely complete, return:

{
  "final": "your factual report"
}
"""


SYSTEM_RULES = """
You are an autonomous software-engineering agent.

Your job is to inspect the ACTUAL repository, understand the task,
make real changes when requested, validate those changes, and give
a factual final report.

STRICT EXECUTION RULES:

1. NEVER invent file paths.
   You must obtain paths from list_files or another repository
   inspection tool.

2. NEVER claim that a file was modified unless write_file actually
   succeeded.

3. NEVER claim that tests were executed unless run_tests actually
   executed.

4. NEVER claim that tests passed unless the actual run_tests result
   indicates success.

5. Before modifying a file:
   - discover its exact path;
   - read its current contents;
   - understand the relevant code.

6. Do not modify a file merely because its name suggests that it
   contains the relevant code.

7. For a modification task, the normal workflow is:

   inspect
   -> read relevant files
   -> understand
   -> modify
   -> run tests
   -> inspect failures
   -> fix if necessary
   -> rerun tests
   -> final report

8. If tests fail because of your change, diagnose the failure and
   attempt a correction before finishing.

9. Keep changes minimal and relevant to the user's task.

10. Do not overwrite unrelated files.

11. Use relative repository paths only.

12. The final report must distinguish:
    - files actually modified;
    - tests actually executed;
    - test result;
    - anything that could not be verified.

13. Do not output fake tool calls as prose.

14. When a tool is needed, output ONLY the JSON tool-call object.

15. Do not finish early simply because you know what change should
    be made. Execute the change.

16. If the user asks for a genuine repository improvement, a final
    answer before write_file is NOT considered completion.
"""


def extract_json(text: str) -> dict[str, Any] | None:
    """
    Extract one JSON object from Gemma's response.
    """

    text = text.strip()

    # Direct JSON.
    try:
        value = json.loads(text)

        if isinstance(value, dict):
            return value

    except json.JSONDecodeError:
        pass

    # Markdown fenced JSON.
    fenced = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if fenced:
        try:
            value = json.loads(fenced.group(1))

            if isinstance(value, dict):
                return value

        except json.JSONDecodeError:
            pass

    # Find first JSON object.
    start = text.find("{")

    if start >= 0:
        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(text)):
            char = text[index]

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False

                continue

            if char == '"':
                in_string = True

            elif char == "{":
                depth += 1

            elif char == "}":
                depth -= 1

                if depth == 0:
                    candidate = text[start:index + 1]

                    try:
                        value = json.loads(candidate)

                        if isinstance(value, dict):
                            return value

                    except json.JSONDecodeError:
                        return None

    return None


# ============================================================
# Task detection
# ============================================================

def task_requires_modification(prompt: str) -> bool:
    text = prompt.lower()

    modification_terms = [
        "modify",
        "change",
        "fix",
        "implement",
        "add",
        "remove",
        "update",
        "refactor",
        "improve",
        "edit",
        "create",
        "correct",
        "repair",
        "patch",
    ]

    return any(term in text for term in modification_terms)


def task_requires_tests(prompt: str) -> bool:
    text = prompt.lower()

    test_terms = [
        "test",
        "tests",
        "pytest",
        "validation",
        "validate",
        "verify",
        "complete test suite",
    ]

    return any(term in text for term in test_terms)


# ============================================================
# Ollama
# ============================================================

def call_ollama(
    model: str,
    messages: list[dict[str, str]],
) -> str:

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.15,
        },
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=300,
    )

    response.raise_for_status()

    data = response.json()

    message = data.get("message", {})
    content = message.get("content", "")

    if not content:
        raise RuntimeError(
            f"Ollama returned no message content: {data}"
        )

    return content


# ============================================================
# Agent
# ============================================================

def run_agent(
    model: str,
    workspace: Path,
    user_prompt: str,
) -> None:

    submission_context = load_submission_context()

    system_prompt = f"""
{SYSTEM_RULES}

{TOOL_DESCRIPTIONS}

LOCAL SUBMISSION CONTEXT:

{submission_context}
"""

    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    requires_modification = task_requires_modification(
        user_prompt
    )

    requires_tests = task_requires_tests(user_prompt)

    did_write = False
    did_test = False

    successful_writes: list[str] = []
    test_results: list[str] = []

    print(f"Model: {model}")
    print(f"Workspace: {workspace}")
    print()

    for step in range(1, MAX_STEPS + 1):

        print(f"--- Agent step {step}/{MAX_STEPS} ---")

        response = call_ollama(
            model,
            messages,
        )

        print("Gemma response:")
        print(truncate_output(response, 5000))
        print()

        parsed = extract_json(response)

        if parsed is None:
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
                        "Your previous response was not a valid tool "
                        "call or final JSON object. Continue the task. "
                        "If a tool is required, return ONLY valid JSON "
                        "using the specified tool-call format."
                    ),
                }
            )

            continue

        # ----------------------------------------------------
        # Tool call
        # ----------------------------------------------------

        if "tool" in parsed:

            tool_name = parsed["tool"]
            arguments = parsed.get("arguments", {})

            if not isinstance(arguments, dict):
                arguments = {}

            print(f"Executing tool: {tool_name}")
            print(f"Arguments: {arguments}")

            try:
                result = execute_tool(
                    workspace,
                    tool_name,
                    arguments,
                )

                if tool_name == "write_file":
                    did_write = True

                    filepath = arguments.get(
                        "filepath",
                        "<unknown>",
                    )

                    successful_writes.append(filepath)

                if tool_name == "run_tests":
                    did_test = True
                    test_results.append(result)

                print("Tool result:")
                print(truncate_output(result, 5000))
                print()

                messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(parsed),
                    }
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"TOOL RESULT ({tool_name}):\n"
                            f"{result}\n\n"
                            "Continue the task using the available "
                            "tools. Do not claim actions that were "
                            "not actually executed."
                        ),
                    }
                )

            except Exception as exc:
                error = (
                    f"TOOL ERROR ({tool_name}): "
                    f"{type(exc).__name__}: {exc}"
                )

                print(error)
                print()

                messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(parsed),
                    }
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"{error}\n"
                            "Correct the tool call and continue."
                        ),
                    }
                )

            continue

        # ----------------------------------------------------
        # Final response
        # ----------------------------------------------------

        if "final" in parsed:

            final_text = str(parsed.get("final", ""))

            # Modification task but no actual write.
            if requires_modification and not did_write:

                print(
                    "GUARD: Gemma attempted to finish before "
                    "performing a real file modification."
                )
                print()

                messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(parsed),
                    }
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You are NOT finished. The task requires "
                            "a real repository modification, but "
                            "write_file has not successfully executed. "
                            "Inspect the exact source file, make the "
                            "requested/genuine improvement with "
                            "write_file, then continue."
                        ),
                    }
                )

                continue

            # Test task but no tests.
            if requires_tests and not did_test:

                print(
                    "GUARD: Gemma attempted to finish before "
                    "running the requested tests."
                )
                print()

                messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(parsed),
                    }
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You are NOT finished. The task requires "
                            "testing, but run_tests has not executed. "
                            "Run the complete test suite now. If tests "
                            "fail, inspect the failure and fix the "
                            "implementation before finishing."
                        ),
                    }
                )

                continue

            print()
            print("=" * 60)
            print("FINAL REPORT")
            print("=" * 60)
            print(final_text)
            print()

            print("ACTUAL EXECUTION SUMMARY")
            print("-" * 60)

            if successful_writes:
                print("Files actually modified:")
                for filepath in successful_writes:
                    print(f"  - {filepath}")
            else:
                print("Files actually modified: none")

            print(
                f"Tests actually executed: "
                f"{'YES' if did_test else 'NO'}"
            )

            if did_test:
                print(
                    "Test executions recorded: "
                    f"{len(test_results)}"
                )

            print("=" * 60)

            return

        # ----------------------------------------------------
        # Unknown JSON
        # ----------------------------------------------------

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
                    "Your JSON did not contain either 'tool' or "
                    "'final'. Continue the task and return a valid "
                    "tool call or final object."
                ),
            }
        )

    print()
    print("=" * 60)
    print("AGENT STOPPED: MAXIMUM STEPS REACHED")
    print("=" * 60)
    print(
        f"Actual writes: "
        f"{len(successful_writes)}"
    )
    print(
        f"Tests actually executed: "
        f"{'YES' if did_test else 'NO'}"
    )


# ============================================================
# CLI
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description="Local Gemma 4 Developer Agent runner"
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Ollama model name.",
    )

    parser.add_argument(
        "--workspace",
        required=True,
        help="Repository workspace.",
    )

    parser.add_argument(
        "--prompt",
        default=None,
        help="One-shot task prompt.",
    )

    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()

    if not workspace.exists():
        raise SystemExit(
            f"Workspace does not exist: {workspace}"
        )

    if not workspace.is_dir():
        raise SystemExit(
            f"Workspace is not a directory: {workspace}"
        )

    prompt = args.prompt

    if not prompt:
        print("Interactive mode.")
        print("Type 'exit' to quit.")
        print()

        while True:
            try:
                prompt = input("Task> ").strip()
            except (EOFError, KeyboardInterrupt):
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
                model=args.model,
                workspace=workspace,
                user_prompt=prompt,
            )

            print()

        return

    run_agent(
        model=args.model,
        workspace=workspace,
        user_prompt=prompt,
    )


if __name__ == "__main__":
    main()

