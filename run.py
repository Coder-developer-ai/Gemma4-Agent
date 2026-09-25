
import argparse
import json
import os
from pathlib import Path

import requests
import yaml




BASE_DIR = Path(__file__).resolve().parent

SYSTEM_PROMPT_FILE = BASE_DIR / "prompts" / "system.md"
LOCALIZATION_FILE = BASE_DIR / "prompts" / "localization.md"
DEBUGGING_FILE = BASE_DIR / "prompts" / "debugging.md"
SAMPLING_FILE = BASE_DIR / "configs" / "sampling.yaml"


OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/chat"
)

MODEL = os.getenv(
    "OLLAMA_MODEL",
    "gemma4:latest"
)


def read_file(path: Path) -> str:
    if not path.exists():
        return ""

    return path.read_text(encoding="utf-8")


def load_sampling_config():
    if not SAMPLING_FILE.exists():
        return {}

    try:
        with open(SAMPLING_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: could not load sampling.yaml: {e}")
        return {}




def build_system_prompt():

    parts = []

    system = read_file(SYSTEM_PROMPT_FILE)
    localization = read_file(LOCALIZATION_FILE)
    debugging = read_file(DEBUGGING_FILE)

    if system:
        parts.append(system)

    if localization:
        parts.append(
            "\n\n--- LOCALIZATION INSTRUCTIONS ---\n"
            + localization
        )

    if debugging:
        parts.append(
            "\n\n--- DEBUGGING INSTRUCTIONS ---\n"
            + debugging
        )

    return "\n".join(parts)




def generate(user_prompt: str):

    sampling = load_sampling_config()

    options = {}

    # Support common Ollama sampling parameters.
    for key in [
        "temperature",
        "top_p",
        "top_k",
        "repeat_penalty",
        "num_ctx",
        "num_predict"
    ]:
        if key in sampling:
            options[key] = sampling[key]

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": build_system_prompt()
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "stream": False,
        "options": options
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=600
        )

        response.raise_for_status()

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Could not connect to Ollama.\n"
            "Make sure Ollama is running."
        )

    except requests.exceptions.HTTPError as e:
        try:
            error = response.json()
            message = error.get("error", str(e))
        except Exception:
            message = str(e)

        raise RuntimeError(f"Ollama error: {message}")

    data = response.json()

    return data["message"]["content"]




def interactive_mode():

 
    print("Gemma Local Agent")

    print(f"Model: {MODEL}")
    print(f"Ollama: {OLLAMA_URL}")
    print()
    print("Type 'exit' or 'quit' to stop.")
    print()

    while True:

        try:
            prompt = input("You: ").strip()

        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not prompt:
            continue

        if prompt.lower() in {"exit", "quit"}:
            break

        try:
            answer = generate(prompt)

            print("\nAgent:")
            print(answer)
            print()

        except Exception as e:
            print(f"\nError: {e}\n")



def main():

    parser = argparse.ArgumentParser(
        description="Run the Gemma agent locally through Ollama."
    )

    parser.add_argument(
        "--prompt",
        type=str,
        help="Run one prompt and exit."
    )

    parser.add_argument(
        "--model",
        type=str,
        help="Override the Ollama model name."
    )

    args = parser.parse_args()

    global MODEL

    if args.model:
        MODEL = args.model

    if args.prompt:
        try:
            print(generate(args.prompt))
        except Exception as e:
            print(f"Error: {e}")
            raise SystemExit(1)

    else:
        interactive_mode()


if __name__ == "__main__":
    main()

