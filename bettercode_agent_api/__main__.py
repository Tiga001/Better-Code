from __future__ import annotations

import argparse
import json
from pathlib import Path

from bettercode_agent_api import analyze_project_for_agent


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m bettercode_agent_api",
        description="Analyze a Python project and emit agent-oriented JSON.",
    )
    parser.add_argument("project_root", type=Path, help="Path to the Python project root.")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON without indentation.",
    )
    arguments = parser.parse_args()
    payload = analyze_project_for_agent(arguments.project_root)
    indent = None if arguments.compact else 2
    print(json.dumps(payload, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
