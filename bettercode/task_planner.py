from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from collections import defaultdict
from pathlib import Path

from bettercode.models import (
    AgentTaskSuitability,
    CodeBlockCall,
    CodeBlockKind,
    CodeBlockSummary,
    DependencyMappingStatus,
    FileDetail,
    ImportKind,
    ProjectGraph,
    SymbolUsage,
    TaskBundle,
    TaskCandidate,
    TaskMode,
    TaskTargetBlock,
)


def build_task_candidates(graph: ProjectGraph) -> dict[str, list[TaskCandidate]]:
    block_lookup, owner_detail_by_block = _block_indexes(graph)
    outgoing_calls = _calls_by_source(graph)
    incoming_calls = _calls_by_target(graph)
    usages_by_target = _usages_by_target(graph)

    candidates_by_block: dict[str, list[TaskCandidate]] = {}
    for block_id, block in block_lookup.items():
        owner_detail = owner_detail_by_block[block_id]
        related_block_ids = sorted(
            {
                candidate_id
                for candidate_id in (
                    [call.target_id for call in outgoing_calls.get(block_id, [])]
                    + [call.source_id for call in incoming_calls.get(block_id, [])]
                    + [
                        usage.owner_block_id
                        for usage in usages_by_target.get(block_id, [])
                        if usage.owner_block_id is not None
                    ]
                )
                if candidate_id is not None and candidate_id != block_id
            }
        )
        related_node_ids = sorted(
            {
                candidate_node_id
                for candidate_node_id in (
                    [owner_detail.node_id]
                    + [call.target_node_id for call in outgoing_calls.get(block_id, [])]
                    + [call.source_node_id for call in incoming_calls.get(block_id, [])]
                    + [usage.source_node_id for usage in usages_by_target.get(block_id, [])]
                )
                if candidate_node_id != owner_detail.node_id
            }
        )

        candidates_by_block[block_id] = [
            _build_optimize_candidate(
                block=block,
                owner_detail=owner_detail,
                related_block_ids=related_block_ids,
                related_node_ids=related_node_ids,
            ),
            _build_translate_candidate(
                block=block,
                owner_detail=owner_detail,
                related_block_ids=related_block_ids,
                related_node_ids=related_node_ids,
            ),
        ]

    return candidates_by_block


def build_task_bundle(graph: ProjectGraph, candidate: TaskCandidate) -> TaskBundle:
    block_lookup, owner_detail_by_block = _block_indexes(graph)
    usages_by_target = _usages_by_target(graph)
    source_cache: dict[Path, list[str]] = {}

    target_block = block_lookup[candidate.target_block_id]
    target_detail = owner_detail_by_block[candidate.target_block_id]

    snippet_block_ids = [candidate.target_block_id, *candidate.related_block_ids]
    source_snippets = [
        _block_excerpt(
            project_root=graph.project.root_path,
            file_detail=owner_detail_by_block[block_id],
            block=block_lookup[block_id],
            source_cache=source_cache,
        )
        for block_id in snippet_block_ids
        if block_id in block_lookup and block_id in owner_detail_by_block
    ]

    related_files = sorted(
        {
            target_detail.path,
            *[
                owner_detail_by_block[block_id].path
                for block_id in candidate.related_block_ids
                if block_id in owner_detail_by_block
            ],
            *[
                graph.file_details[node_id].path
                for node_id in candidate.related_node_ids
                if node_id in graph.file_details
            ],
        }
    )
    related_blocks = [
        _block_label(block_lookup[block_id], owner_detail_by_block[block_id])
        for block_id in snippet_block_ids
        if block_id in block_lookup and block_id in owner_detail_by_block
    ]
    target_blocks = [
        _target_block(
            project_root=graph.project.root_path,
            file_detail=target_detail,
            block=target_block,
            source_cache=source_cache,
        )
    ]

    return TaskBundle(
        task=candidate,
        source_snippets=source_snippets,
        related_files=related_files,
        related_blocks=related_blocks,
        target_blocks=target_blocks,
        usages=list(usages_by_target.get(candidate.target_block_id, [])),
        dependencies=list(target_detail.imports),
        constraints=list(candidate.constraints),
        acceptance_checks=list(candidate.acceptance_checks),
        editable_files=[target_detail.path],
        context_files=[path for path in related_files if path != target_detail.path],
    )


def task_bundle_to_dict(bundle: TaskBundle) -> dict[str, object]:
    return _json_ready(bundle)


def _build_optimize_candidate(
    *,
    block: CodeBlockSummary,
    owner_detail: FileDetail,
    related_block_ids: list[str],
    related_node_ids: list[str],
) -> TaskCandidate:
    reasons = list(block.agent_task_reasons) or ["existing code-block analysis marked this block as workable"]
    constraints = [
        "Preserve Python behavior and public interfaces.",
        "Keep changes local unless dependent callers must be updated.",
    ]
    if related_block_ids or related_node_ids:
        constraints.append("Review adjacent blocks and dependent files before changing signatures.")
    acceptance_checks = [
        "Run Python tests covering the target block.",
        "Keep the project free of new syntax errors.",
    ]
    return TaskCandidate(
        id=f"{block.id}:optimize",
        mode=TaskMode.OPTIMIZE,
        target_block_id=block.id,
        target_node_id=owner_detail.node_id,
        source_language="python",
        target_language=None,
        suitability=block.agent_task_fit,
        related_block_ids=related_block_ids,
        related_node_ids=related_node_ids,
        reasons=reasons,
        constraints=constraints,
        acceptance_checks=acceptance_checks,
    )


def _build_translate_candidate(
    *,
    block: CodeBlockSummary,
    owner_detail: FileDetail,
    related_block_ids: list[str],
    related_node_ids: list[str],
) -> TaskCandidate:
    suitability = AgentTaskSuitability.GOOD
    reasons: list[str] = []
    mapping_status = DependencyMappingStatus.MAPPED

    external_imports = [record for record in owner_detail.imports if record.kind is ImportKind.EXTERNAL]
    unresolved_imports = [record for record in owner_detail.imports if record.kind is ImportKind.UNRESOLVED]

    if owner_detail.syntax_error:
        suitability = AgentTaskSuitability.AVOID
        mapping_status = DependencyMappingStatus.BLOCKED
        reasons.append("file currently has syntax errors, so translation cannot be validated safely")

    if block.kind is CodeBlockKind.MODULE_SCOPE:
        suitability = AgentTaskSuitability.AVOID
        reasons.append("module-scope execution blocks are not part of the translation MVP yet")
    elif block.kind is not CodeBlockKind.FUNCTION or block.parent_id is not None:
        suitability = AgentTaskSuitability.AVOID
        reasons.append("function-level translation MVP only supports top-level functions")

    if block.agent_task_fit is AgentTaskSuitability.AVOID:
        suitability = AgentTaskSuitability.AVOID
        reasons.append("existing task-fit analysis already marks this block as tightly coupled")
    elif block.agent_task_fit is AgentTaskSuitability.CAUTION:
        suitability = _downgrade_suitability(suitability, AgentTaskSuitability.CAUTION)
        reasons.append("existing task-fit analysis says surrounding context still matters")

    if external_imports:
        mapping_status = DependencyMappingStatus.CANDIDATE
        suitability = _downgrade_suitability(suitability, AgentTaskSuitability.CAUTION)
        reasons.append(f"{len(external_imports)} external import(s) need confirmed C++ library mappings")

    if unresolved_imports:
        mapping_status = DependencyMappingStatus.STUB_REQUIRED
        suitability = _downgrade_suitability(suitability, AgentTaskSuitability.CAUTION)
        reasons.append(f"{len(unresolved_imports)} unresolved import(s) may need interface stubs")

    if not reasons:
        reasons.append("top-level function has a stable enough boundary for translation MVP")

    constraints = [
        "Preserve the Python function signature and observable behavior.",
        "Keep surrounding file structure stable while introducing the translated C++ boundary.",
        "Generate output that fits a CMake + C++20 project layout.",
    ]
    if mapping_status is DependencyMappingStatus.CANDIDATE:
        constraints.append("Confirm Python-to-C++ dependency mappings before finalizing translation.")
    elif mapping_status is DependencyMappingStatus.STUB_REQUIRED:
        constraints.append("Generate explicit interface stubs for dependencies that cannot be mapped automatically.")

    acceptance_checks = [
        "Compile the generated C++20 target.",
        "Run equivalence tests for the translated function against the Python original.",
        "Keep the translated interface compatible with the remaining Python-side workflow.",
    ]

    return TaskCandidate(
        id=f"{block.id}:translate",
        mode=TaskMode.TRANSLATE,
        target_block_id=block.id,
        target_node_id=owner_detail.node_id,
        source_language="python",
        target_language="cpp",
        suitability=suitability,
        related_block_ids=related_block_ids,
        related_node_ids=related_node_ids,
        reasons=reasons,
        constraints=constraints,
        acceptance_checks=acceptance_checks,
        dependency_mapping_status=mapping_status,
    )


def _downgrade_suitability(
    current: AgentTaskSuitability,
    proposed: AgentTaskSuitability,
) -> AgentTaskSuitability:
    order = {
        AgentTaskSuitability.GOOD: 0,
        AgentTaskSuitability.CAUTION: 1,
        AgentTaskSuitability.AVOID: 2,
    }
    return proposed if order[proposed] > order[current] else current


def _block_indexes(graph: ProjectGraph) -> tuple[dict[str, CodeBlockSummary], dict[str, FileDetail]]:
    block_lookup: dict[str, CodeBlockSummary] = {}
    owner_detail_by_block: dict[str, FileDetail] = {}
    for detail in graph.file_details.values():
        for block in detail.code_blocks:
            block_lookup[block.id] = block
            owner_detail_by_block[block.id] = detail
    return block_lookup, owner_detail_by_block


def _calls_by_source(graph: ProjectGraph) -> dict[str, list[CodeBlockCall]]:
    call_map: dict[str, list[CodeBlockCall]] = defaultdict(list)
    for detail in graph.file_details.values():
        for call in detail.code_block_calls:
            call_map[call.source_id].append(call)
    return dict(call_map)


def _calls_by_target(graph: ProjectGraph) -> dict[str, list[CodeBlockCall]]:
    call_map: dict[str, list[CodeBlockCall]] = defaultdict(list)
    for detail in graph.file_details.values():
        for call in detail.code_block_calls:
            call_map[call.target_id].append(call)
    return dict(call_map)


def _usages_by_target(graph: ProjectGraph) -> dict[str, list[SymbolUsage]]:
    usage_map: dict[str, list[SymbolUsage]] = defaultdict(list)
    for detail in graph.file_details.values():
        for usage in detail.symbol_usages:
            usage_map[usage.target_id].append(usage)
    return dict(usage_map)


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


def _target_block(
    *,
    project_root: Path,
    file_detail: FileDetail,
    block: CodeBlockSummary,
    source_cache: dict[Path, list[str]],
) -> TaskTargetBlock:
    return TaskTargetBlock(
        id=block.id,
        path=file_detail.path,
        kind=block.kind,
        name=block.name,
        signature=block.signature,
        start_line=block.line,
        end_line=block.end_line,
        source_text=_block_source_text(
            project_root=project_root,
            file_detail=file_detail,
            block=block,
            source_cache=source_cache,
        ),
    )


def _block_source_text(
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
    return "\n".join(lines[max(block.line - 1, 0) : min(block.end_line, len(lines))])


def _json_ready(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _json_ready(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value
