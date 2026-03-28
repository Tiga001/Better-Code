# bettercode/cli/cmd_analyze_project.py
from __future__ import annotations

import json
from pathlib import Path

import typer

from bettercode_agent_api import analyze_project_for_agent


def analyze_project(
    project_root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    pretty: bool = typer.Option(True, "--pretty/--compact", help="Pretty-print JSON output."),
) -> None:
    """
    Analyze a Python project and emit agent-oriented JSON to stdout.
    """
    payload = analyze_project_for_agent(project_root)
    indent = 2 if pretty else None
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=indent))
