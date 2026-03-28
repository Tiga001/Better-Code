from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from bettercode_agent_api.graph_analysis import analyze_graph_structure, decompose_subsystems
from bettercode_agent_api.models import ImportKind, NodeKind, ProjectGraph
from bettercode_agent_api.models import TaskMode
from bettercode_agent_api.parser import ProjectAnalyzer
from bettercode_agent_api.task_graph import (
    build_task_batch,
    build_task_execution_plan,
    build_task_graph,
    task_batch_to_dict,
    task_execution_plan_to_dict,
    task_graph_to_dict,
)

SCHEMA_VERSION = "1.0"
ANALYSIS_MODE = "static"
LIMITATIONS = [
    "Dynamic imports, eval, exec, getattr/setattr dispatch, monkey patching, and runtime-only behavior are not resolved precisely.",
    "All dependency, task, and phase outputs are derived from static analysis without runtime tracing.",
    "Task and batch outputs are planning artifacts; they do not imply that optimization or translation has been executed.",
]


def analyze_project_for_agent(project_root: str | Path) -> dict[str, Any]:
    root_path = Path(project_root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Project root does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Project root is not a directory: {root_path}")

    graph = ProjectAnalyzer().analyze(root_path)
    insights = analyze_graph_structure(graph)
    subsystem_summaries = decompose_subsystems(graph)
    task_graph = build_task_graph(graph)
    optimize_plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
    translate_plan = build_task_execution_plan(graph, mode=TaskMode.TRANSLATE)
    optimize_batch = build_task_batch(graph, mode=TaskMode.OPTIMIZE)
    translate_batch = build_task_batch(graph, mode=TaskMode.TRANSLATE)

    return {
        "schema_version": SCHEMA_VERSION,
        "analysis_mode": ANALYSIS_MODE,
        "generated_at": datetime.now(UTC).isoformat(),
        "project_root": str(root_path),
        "project_name": graph.project.name,
        "issues": _build_issues(graph),
        "dependency_graph": _build_dependency_graph_payload(graph, insights),
        "subsystem_graph": _build_subsystem_graph_payload(graph, subsystem_summaries),
        "task_graph": {
            "graph": task_graph_to_dict(task_graph),
            "plans": {
                "optimize": task_execution_plan_to_dict(optimize_plan),
                "translate": task_execution_plan_to_dict(translate_plan),
            },
        },
        "batch_view": {
            "optimize": task_batch_to_dict(optimize_batch),
            "translate": task_batch_to_dict(translate_batch),
        },
    }


def _build_dependency_graph_payload(graph: ProjectGraph, insights: Any) -> dict[str, Any]:
    node_kind_by_id = {node.id: node.kind for node in graph.nodes}
    file_details: dict[str, Any] = {}
    for detail in sorted(graph.file_details.values(), key=lambda current: current.path.lower()):
        payload = _json_ready(detail)
        payload["node_kind"] = node_kind_by_id[detail.node_id].value
        file_details[detail.path] = payload

    return {
        "project": _json_ready(graph.project),
        "nodes": _json_ready(graph.nodes),
        "edges": _json_ready(graph.edges),
        "file_details": file_details,
        "insights": _json_ready(insights),
    }


def _build_subsystem_graph_payload(graph: ProjectGraph, subsystem_summaries: list[Any]) -> dict[str, Any]:
    nodes_by_id = {node.id: node for node in graph.nodes}
    subsystem_by_node_id: dict[str, str] = {}
    subsystems: list[dict[str, Any]] = []

    for summary in subsystem_summaries:
        subsystem_id = f"subsystem:{summary.index}"
        node_ids = list(summary.node_ids)
        member_node_ids = set(node_ids)
        member_edges = [
            edge
            for edge in graph.edges
            if edge.source in member_node_ids and edge.target in member_node_ids
        ]
        entry_node_ids = sorted(
            node_id
            for node_id in node_ids
            if not any(edge.target == node_id and edge.source in member_node_ids for edge in member_edges)
        )
        leaf_node_ids = sorted(
            node_id
            for node_id in node_ids
            if not any(edge.source == node_id and edge.target in member_node_ids for edge in member_edges)
        )
        external_dependency_node_ids = sorted(
            {
                edge.target
                for edge in graph.edges
                if edge.source in member_node_ids
                and edge.target in nodes_by_id
                and nodes_by_id[edge.target].kind is NodeKind.EXTERNAL_PACKAGE
            }
        )
        subsystem_payload = {
            "id": subsystem_id,
            "index": summary.index,
            "node_ids": node_ids,
            "member_paths": list(summary.member_paths),
            "member_nodes": _json_ready([nodes_by_id[node_id] for node_id in node_ids if node_id in nodes_by_id]),
            "member_edges": _json_ready(member_edges),
            "entry_node_ids": entry_node_ids,
            "leaf_node_ids": leaf_node_ids,
            "external_dependency_node_ids": external_dependency_node_ids,
        }
        for node_id in node_ids:
            subsystem_by_node_id[node_id] = subsystem_id
        subsystems.append(subsystem_payload)

    return {
        "subsystems": subsystems,
        "cross_subsystem_edges": [
            _json_ready(edge)
            for edge in graph.edges
            if edge.source in subsystem_by_node_id
            and edge.target in subsystem_by_node_id
            and subsystem_by_node_id[edge.source] != subsystem_by_node_id[edge.target]
        ],
    }


def _build_issues(graph: ProjectGraph) -> dict[str, Any]:
    syntax_errors: list[dict[str, Any]] = []
    unresolved_imports: list[dict[str, Any]] = []
    for detail in sorted(graph.file_details.values(), key=lambda current: current.path.lower()):
        if detail.syntax_error:
            syntax_errors.append(
                {
                    "path": detail.path,
                    "node_id": detail.node_id,
                    "module": detail.module,
                    "error": detail.syntax_error,
                }
            )
        for import_record in detail.imports:
            if import_record.kind is not ImportKind.UNRESOLVED:
                continue
            unresolved_imports.append(
                {
                    "path": detail.path,
                    "node_id": detail.node_id,
                    "module": import_record.module,
                    "line": import_record.line,
                }
            )

    return {
        "parse_error_count": graph.project.parse_errors,
        "syntax_errors": syntax_errors,
        "unresolved_imports": unresolved_imports,
        "limitations": list(LIMITATIONS),
    }


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _json_ready(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value
