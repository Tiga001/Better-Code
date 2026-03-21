from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path

from bettercode.models import (
    AgentTaskSuitability,
    CodeBlockKind,
    CodeBlockSummary,
    FileDetail,
    ImportKind,
    ProjectGraph,
    TaskExecutionPlan,
    TaskGraph,
    TaskGraphEdge,
    TaskGraphUnit,
    TaskMode,
    TaskUnitPackage,
    TaskQueueItem,
    TaskUnitKind,
)
from bettercode.task_planner import build_task_candidates


def build_task_graph(graph: ProjectGraph) -> TaskGraph:
    block_lookup, owner_detail_by_block = _block_indexes(graph)
    base_units, block_to_unit_id = _build_base_units(block_lookup, owner_detail_by_block)
    base_edges = _build_base_edges(
        graph=graph,
        base_units=base_units,
        block_to_unit_id=block_to_unit_id,
        owner_detail_by_block=owner_detail_by_block,
    )
    merged_units, merged_edges = _collapse_cycles(base_units, base_edges)
    depths = _compute_depths(merged_units, merged_edges)
    depended_on_by = _reverse_dependencies(merged_units, merged_edges)

    units = [
        TaskGraphUnit(
            id=unit.id,
            kind=unit.kind,
            label=unit.label,
            block_ids=list(unit.block_ids),
            root_block_ids=list(unit.root_block_ids),
            node_ids=list(unit.node_ids),
            depends_on=sorted({edge.target for edge in merged_edges if edge.source == unit.id}),
            depended_on_by=sorted(depended_on_by.get(unit.id, set())),
            depth=depths[unit.id],
            reasons=list(unit.reasons),
            ready_to_run=not any(edge.source == unit.id for edge in merged_edges),
        )
        for unit in _sort_units(merged_units, depths, depended_on_by)
    ]
    edges = sorted(merged_edges, key=lambda edge: (depths[edge.source], edge.source, edge.target))
    return TaskGraph(units=units, edges=edges)


def build_task_execution_plan(graph: ProjectGraph, *, mode: TaskMode) -> TaskExecutionPlan:
    task_graph = build_task_graph(graph)
    candidates_by_block = build_task_candidates(graph)
    units_by_id = {unit.id: unit for unit in task_graph.units}

    ordered_units = sorted(
        task_graph.units,
        key=lambda unit: (unit.depth, -len(unit.depended_on_by), unit.label.lower(), unit.id),
    )
    items: list[TaskQueueItem] = []
    for index, unit in enumerate(ordered_units, start=1):
        unit_candidates = [
            candidate
            for block_id in unit.root_block_ids
            for candidate in candidates_by_block.get(block_id, [])
            if candidate.mode is mode
        ]
        suitability = _aggregate_suitability(unit_candidates)
        reasons = _aggregate_reasons(unit, unit_candidates, task_graph)
        item_id = f"{unit.id}:{mode.value}"
        items.append(
            TaskQueueItem(
                id=item_id,
                unit_id=unit.id,
                mode=mode,
                label=unit.label,
                target_block_ids=list(unit.block_ids),
                target_node_ids=list(unit.node_ids),
                depends_on=[f"{dependency_id}:{mode.value}" for dependency_id in unit.depends_on],
                depended_on_by=[f"{dependent_id}:{mode.value}" for dependent_id in unit.depended_on_by],
                depth=unit.depth,
                order_index=index,
                suitability=suitability,
                risk=suitability,
                reasons=reasons,
                ready_to_run=unit.ready_to_run,
            )
        )
    return TaskExecutionPlan(mode=mode, items=items)


def task_graph_to_dict(task_graph: TaskGraph) -> dict[str, object]:
    return _json_ready(task_graph)


def task_execution_plan_to_dict(plan: TaskExecutionPlan) -> dict[str, object]:
    return _json_ready(plan)


def build_task_unit_package(
    graph: ProjectGraph,
    *,
    unit_id: str,
    mode: TaskMode,
) -> TaskUnitPackage:
    task_graph = build_task_graph(graph)
    units_by_id = {unit.id: unit for unit in task_graph.units}
    if unit_id not in units_by_id:
        raise KeyError(f"Unknown task unit: {unit_id}")
    unit = units_by_id[unit_id]
    plan = build_task_execution_plan(graph, mode=mode)
    item_lookup = {item.unit_id: item for item in plan.items}
    if unit_id not in item_lookup:
        raise KeyError(f"No execution plan item for unit: {unit_id}")
    item = item_lookup[unit_id]

    block_lookup, owner_detail_by_block = _block_indexes(graph)
    source_cache: dict[Path, list[str]] = {}
    related_files = sorted(
        {
            owner_detail_by_block[block_id].path
            for block_id in unit.block_ids
            if block_id in owner_detail_by_block
        }
    )
    related_blocks = [
        _block_label(block_lookup[block_id], owner_detail_by_block[block_id])
        for block_id in unit.block_ids
        if block_id in block_lookup and block_id in owner_detail_by_block
    ]
    source_snippets = [
        _block_excerpt(
            project_root=graph.project.root_path,
            file_detail=owner_detail_by_block[block_id],
            block=block_lookup[block_id],
            source_cache=source_cache,
        )
        for block_id in unit.block_ids
        if block_id in block_lookup and block_id in owner_detail_by_block
    ]

    candidates_by_block = build_task_candidates(graph)
    constraints: list[str] = []
    acceptance_checks: list[str] = []
    for block_id in unit.root_block_ids:
        for candidate in candidates_by_block.get(block_id, []):
            if candidate.mode is not mode:
                continue
            for constraint in candidate.constraints:
                if constraint not in constraints:
                    constraints.append(constraint)
            for check in candidate.acceptance_checks:
                if check not in acceptance_checks:
                    acceptance_checks.append(check)

    return TaskUnitPackage(
        item=item,
        related_files=related_files,
        related_blocks=related_blocks,
        source_snippets=source_snippets,
        constraints=constraints,
        acceptance_checks=acceptance_checks,
        prerequisites=list(item.depends_on),
    )


def task_unit_package_to_dict(package: TaskUnitPackage) -> dict[str, object]:
    return _json_ready(package)


class _TaskUnitDraft:
    def __init__(
        self,
        *,
        id: str,
        kind: TaskUnitKind,
        label: str,
        block_ids: list[str],
        root_block_ids: list[str],
        node_ids: list[str],
        reasons: list[str],
    ) -> None:
        self.id = id
        self.kind = kind
        self.label = label
        self.block_ids = block_ids
        self.root_block_ids = root_block_ids
        self.node_ids = node_ids
        self.reasons = reasons


def _build_base_units(
    block_lookup: dict[str, CodeBlockSummary],
    owner_detail_by_block: dict[str, FileDetail],
) -> tuple[dict[str, _TaskUnitDraft], dict[str, str]]:
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for block in block_lookup.values():
        if block.parent_id is not None:
            children_by_parent[block.parent_id].append(block.id)

    seed_ids = {
        block.id
        for block in block_lookup.values()
        if (block.kind is CodeBlockKind.CLASS and block.parent_id is None)
        or (block.kind is CodeBlockKind.FUNCTION and block.parent_id is None)
    }

    block_to_seed_id: dict[str, str] = {}
    for block_id, block in block_lookup.items():
        current = block
        assigned_seed_id: str | None = None
        while current is not None:
            if current.id in seed_ids:
                assigned_seed_id = current.id
                break
            if current.parent_id is None or current.parent_id not in block_lookup:
                break
            current = block_lookup[current.parent_id]
        if assigned_seed_id is None:
            assigned_seed_id = block.id
            seed_ids.add(block.id)
        block_to_seed_id[block_id] = assigned_seed_id

    blocks_by_seed_id: dict[str, list[str]] = defaultdict(list)
    for block_id, seed_id in block_to_seed_id.items():
        blocks_by_seed_id[seed_id].append(block_id)

    base_units: dict[str, _TaskUnitDraft] = {}
    block_to_unit_id: dict[str, str] = {}
    for seed_id in sorted(seed_ids):
        seed_block = block_lookup[seed_id]
        owner_detail = owner_detail_by_block[seed_id]
        unit_block_ids = sorted(blocks_by_seed_id[seed_id], key=lambda candidate_id: _sort_key(block_lookup[candidate_id]))
        unit_id = f"task_unit:{seed_id}"
        label = _unit_label(seed_block, owner_detail)
        kind = TaskUnitKind.CLASS_GROUP if seed_block.kind is CodeBlockKind.CLASS else TaskUnitKind.FUNCTION
        reasons = [_seed_reason(seed_block)]
        base_units[unit_id] = _TaskUnitDraft(
            id=unit_id,
            kind=kind,
            label=label,
            block_ids=unit_block_ids,
            root_block_ids=[seed_id],
            node_ids=[owner_detail.node_id],
            reasons=reasons,
        )
        for block_id in unit_block_ids:
            block_to_unit_id[block_id] = unit_id

    return base_units, block_to_unit_id


def _build_base_edges(
    *,
    graph: ProjectGraph,
    base_units: dict[str, _TaskUnitDraft],
    block_to_unit_id: dict[str, str],
    owner_detail_by_block: dict[str, FileDetail],
) -> list[TaskGraphEdge]:
    edge_reasons: dict[tuple[str, str], set[str]] = defaultdict(set)
    units_by_node_id: dict[str, set[str]] = defaultdict(set)
    for unit in base_units.values():
        for node_id in unit.node_ids:
            units_by_node_id[node_id].add(unit.id)

    for detail in graph.file_details.values():
        for call in detail.code_block_calls:
            source_unit_id = block_to_unit_id.get(call.source_id)
            target_unit_id = block_to_unit_id.get(call.target_id)
            if source_unit_id is None or target_unit_id is None or source_unit_id == target_unit_id:
                continue
            reason = "cross-file call" if call.is_cross_file else "call"
            edge_reasons[(source_unit_id, target_unit_id)].add(reason)

        for usage in detail.symbol_usages:
            if usage.owner_block_id is None:
                continue
            source_unit_id = block_to_unit_id.get(usage.owner_block_id)
            target_unit_id = block_to_unit_id.get(usage.target_id)
            if source_unit_id is None or target_unit_id is None or source_unit_id == target_unit_id:
                continue
            edge_reasons[(source_unit_id, target_unit_id)].add(f"usage:{usage.usage_kind.value}")

        source_unit_ids = units_by_node_id.get(detail.node_id, set())
        if not source_unit_ids:
            continue
        for import_record in detail.imports:
            if import_record.kind is not ImportKind.INTERNAL or not import_record.target_node_id:
                continue
            target_unit_ids = units_by_node_id.get(import_record.target_node_id, set())
            for source_unit_id in source_unit_ids:
                for target_unit_id in target_unit_ids:
                    if source_unit_id == target_unit_id:
                        continue
                    edge_reasons[(source_unit_id, target_unit_id)].add("file import")

    return [
        TaskGraphEdge(source=source, target=target, reasons=sorted(reasons))
        for (source, target), reasons in sorted(edge_reasons.items())
    ]


def _collapse_cycles(
    base_units: dict[str, _TaskUnitDraft],
    base_edges: list[TaskGraphEdge],
) -> tuple[dict[str, _TaskUnitDraft], list[TaskGraphEdge]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in base_edges:
        adjacency[edge.source].append(edge.target)
    for unit_id in base_units:
        adjacency.setdefault(unit_id, [])

    components = _strongly_connected_components(adjacency)
    unit_to_component: dict[str, str] = {}
    merged_units: dict[str, _TaskUnitDraft] = {}

    for component_index, component in enumerate(components, start=1):
        sorted_members = sorted(component)
        if len(sorted_members) == 1:
            member_id = sorted_members[0]
            merged_units[member_id] = base_units[member_id]
            unit_to_component[member_id] = member_id
            continue

        member_units = [base_units[member_id] for member_id in sorted_members]
        merged_id = f"task_unit:cycle_group:{component_index}"
        labels = [member.label for member in member_units]
        label = labels[0] if len(labels) == 1 else f"{labels[0]} +{len(labels) - 1}"
        merged_units[merged_id] = _TaskUnitDraft(
            id=merged_id,
            kind=TaskUnitKind.CYCLE_GROUP,
            label=label,
            block_ids=sorted({block_id for member in member_units for block_id in member.block_ids}),
            root_block_ids=sorted({block_id for member in member_units for block_id in member.root_block_ids}),
            node_ids=sorted({node_id for member in member_units for node_id in member.node_ids}),
            reasons=["mutual internal dependencies merged these blocks into one task group"],
        )
        for member_id in sorted_members:
            unit_to_component[member_id] = merged_id

    collapsed_edge_reasons: dict[tuple[str, str], set[str]] = defaultdict(set)
    for edge in base_edges:
        source = unit_to_component[edge.source]
        target = unit_to_component[edge.target]
        if source == target:
            continue
        collapsed_edge_reasons[(source, target)].update(edge.reasons)

    merged_edges = [
        TaskGraphEdge(source=source, target=target, reasons=sorted(reasons))
        for (source, target), reasons in sorted(collapsed_edge_reasons.items())
    ]
    return merged_units, merged_edges


def _compute_depths(units: dict[str, _TaskUnitDraft], edges: list[TaskGraphEdge]) -> dict[str, int]:
    dependencies: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        dependencies[edge.source].add(edge.target)
    for unit_id in units:
        dependencies.setdefault(unit_id, set())

    cache: dict[str, int] = {}

    def compute(unit_id: str) -> int:
        if unit_id in cache:
            return cache[unit_id]
        if not dependencies[unit_id]:
            cache[unit_id] = 0
            return 0
        depth = 1 + max(compute(dependency_id) for dependency_id in dependencies[unit_id])
        cache[unit_id] = depth
        return depth

    for unit_id in units:
        compute(unit_id)
    return cache


def _reverse_dependencies(units: dict[str, _TaskUnitDraft], edges: list[TaskGraphEdge]) -> dict[str, set[str]]:
    depended_on_by: dict[str, set[str]] = {unit_id: set() for unit_id in units}
    for edge in edges:
        depended_on_by.setdefault(edge.target, set())
        depended_on_by.setdefault(edge.source, set())
        depended_on_by[edge.target].add(edge.source)
    return depended_on_by


def _aggregate_suitability(unit_candidates) -> AgentTaskSuitability:
    if not unit_candidates:
        return AgentTaskSuitability.CAUTION
    order = {
        AgentTaskSuitability.GOOD: 0,
        AgentTaskSuitability.CAUTION: 1,
        AgentTaskSuitability.AVOID: 2,
    }
    return max(unit_candidates, key=lambda candidate: order[candidate.suitability]).suitability


def _aggregate_reasons(unit: TaskGraphUnit, unit_candidates, task_graph: TaskGraph) -> list[str]:
    reasons: list[str] = []
    for reason in unit.reasons:
        if reason not in reasons:
            reasons.append(reason)
    for candidate in unit_candidates:
        for reason in candidate.reasons:
            if reason not in reasons:
                reasons.append(reason)
    edge_reason_map = {
        edge.target: edge.reasons
        for edge in task_graph.edges
        if edge.source == unit.id
    }
    for dependency_id in unit.depends_on:
        dependency_reasons = edge_reason_map.get(dependency_id, [])
        if dependency_reasons:
            summary = ", ".join(dependency_reasons[:2])
            reasons.append(f"depends on {dependency_id} via {summary}")
        else:
            reasons.append(f"depends on {dependency_id}")
    return reasons


def _sort_units(
    units: dict[str, _TaskUnitDraft],
    depths: dict[str, int],
    depended_on_by: dict[str, set[str]],
) -> list[_TaskUnitDraft]:
    return sorted(
        units.values(),
        key=lambda unit: (depths[unit.id], -len(depended_on_by.get(unit.id, set())), unit.label.lower(), unit.id),
    )


def _block_indexes(graph: ProjectGraph) -> tuple[dict[str, CodeBlockSummary], dict[str, FileDetail]]:
    block_lookup: dict[str, CodeBlockSummary] = {}
    owner_detail_by_block: dict[str, FileDetail] = {}
    for detail in graph.file_details.values():
        for block in detail.code_blocks:
            block_lookup[block.id] = block
            owner_detail_by_block[block.id] = detail
    return block_lookup, owner_detail_by_block


def _block_excerpt(
    *,
    project_root: Path,
    file_detail: FileDetail,
    block: CodeBlockSummary,
    source_cache: dict[Path, list[str]],
) -> str:
    file_path = project_root / file_detail.path
    if file_path not in source_cache:
        try:
            source_cache[file_path] = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            source_cache[file_path] = []
    lines = source_cache[file_path]
    excerpt = "\n".join(lines[max(block.line - 1, 0) : min(block.end_line, len(lines))])
    header = f"{file_detail.path}:{block.line}-{block.end_line} {block.signature or block.name}"
    return f"{header}\n{excerpt}" if excerpt else header


def _block_label(block: CodeBlockSummary, file_detail: FileDetail) -> str:
    return f"{block.signature or block.name} [{file_detail.path}]"


def _unit_label(block: CodeBlockSummary, owner_detail: FileDetail) -> str:
    return f"{block.signature or block.name} [{owner_detail.path}]"


def _seed_reason(block: CodeBlockSummary) -> str:
    if block.kind is CodeBlockKind.CLASS:
        return "class methods are grouped into one task unit"
    return "top-level function is a standalone task unit"


def _sort_key(block: CodeBlockSummary) -> tuple[int, str]:
    return (block.line, block.name)


def _strongly_connected_components(adjacency: dict[str, list[str]]) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    in_stack: set[str] = set()
    components: list[list[str]] = []

    def strongconnect(node_id: str) -> None:
        nonlocal index
        indices[node_id] = index
        lowlinks[node_id] = index
        index += 1
        stack.append(node_id)
        in_stack.add(node_id)

        for neighbor_id in adjacency.get(node_id, []):
            if neighbor_id not in indices:
                strongconnect(neighbor_id)
                lowlinks[node_id] = min(lowlinks[node_id], lowlinks[neighbor_id])
            elif neighbor_id in in_stack:
                lowlinks[node_id] = min(lowlinks[node_id], indices[neighbor_id])

        if lowlinks[node_id] == indices[node_id]:
            component: list[str] = []
            while stack:
                member_id = stack.pop()
                in_stack.remove(member_id)
                component.append(member_id)
                if member_id == node_id:
                    break
            components.append(component)

    for node_id in sorted(adjacency):
        if node_id not in indices:
            strongconnect(node_id)
    return components


def _json_ready(value):
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
