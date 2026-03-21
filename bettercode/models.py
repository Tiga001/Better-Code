from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class NodeKind(str, Enum):
    EXTERNAL_PACKAGE = "external_package"
    PYTHON_FILE = "python_file"
    LEAF_FILE = "leaf_file"
    TOP_LEVEL_SCRIPT = "top_level_script"


class ImportKind(str, Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    STANDARD_LIBRARY = "standard_library"
    UNRESOLVED = "unresolved"


class CodeBlockKind(str, Enum):
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class AgentTaskSuitability(str, Enum):
    GOOD = "good"
    CAUTION = "caution"
    AVOID = "avoid"


class TaskMode(str, Enum):
    OPTIMIZE = "optimize"
    TRANSLATE = "translate"


class TaskUnitKind(str, Enum):
    FUNCTION = "function"
    CLASS_GROUP = "class_group"
    CYCLE_GROUP = "cycle_group"


class DependencyMappingStatus(str, Enum):
    MAPPED = "mapped"
    CANDIDATE = "candidate"
    STUB_REQUIRED = "stub_required"
    BLOCKED = "blocked"


class UsageKind(str, Enum):
    CALL = "call"
    METHOD_CALL = "method_call"
    INSTANTIATION = "instantiation"
    INHERITANCE = "inheritance"
    DECORATOR = "decorator"
    TYPE_ANNOTATION = "type_annotation"
    IMPORT = "import"


class UsageConfidence(str, Enum):
    EXACT = "exact"
    PROBABLE = "probable"


@dataclass(slots=True)
class ImportRecord:
    module: str
    line: int
    kind: ImportKind
    target_node_id: str | None = None


@dataclass(slots=True)
class ClassSummary:
    name: str
    line: int


@dataclass(slots=True)
class FunctionSummary:
    name: str
    line: int


@dataclass(slots=True)
class CodeBlockSummary:
    id: str
    kind: CodeBlockKind
    name: str
    line: int
    end_line: int
    depth: int
    parent_id: str | None = None
    signature: str | None = None
    parameters: list[str] = field(default_factory=list)
    return_summary: str | None = None
    agent_task_fit: AgentTaskSuitability = AgentTaskSuitability.CAUTION
    agent_task_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CodeBlockCall:
    source_id: str
    source_node_id: str
    target_id: str
    target_node_id: str
    line: int
    expression: str
    is_cross_file: bool = False


@dataclass(slots=True)
class SymbolUsage:
    target_id: str
    target_node_id: str
    source_node_id: str
    line: int
    expression: str
    usage_kind: UsageKind
    confidence: UsageConfidence
    owner_block_id: str | None = None
    is_cross_file: bool = False


@dataclass(slots=True)
class TaskCandidate:
    id: str
    mode: TaskMode
    target_block_id: str
    target_node_id: str
    source_language: str
    target_language: str | None
    suitability: AgentTaskSuitability
    related_block_ids: list[str] = field(default_factory=list)
    related_node_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    acceptance_checks: list[str] = field(default_factory=list)
    dependency_mapping_status: DependencyMappingStatus | None = None


@dataclass(slots=True)
class TaskBundle:
    task: TaskCandidate
    source_snippets: list[str]
    related_files: list[str]
    related_blocks: list[str]
    usages: list[SymbolUsage]
    dependencies: list[ImportRecord]
    constraints: list[str]
    acceptance_checks: list[str]


@dataclass(slots=True)
class TaskGraphUnit:
    id: str
    kind: TaskUnitKind
    label: str
    block_ids: list[str]
    root_block_ids: list[str]
    node_ids: list[str]
    depends_on: list[str]
    depended_on_by: list[str]
    depth: int
    reasons: list[str] = field(default_factory=list)
    ready_to_run: bool = False


@dataclass(slots=True)
class TaskGraphEdge:
    source: str
    target: str
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskGraph:
    units: list[TaskGraphUnit]
    edges: list[TaskGraphEdge]


@dataclass(slots=True)
class TaskQueueItem:
    id: str
    unit_id: str
    mode: TaskMode
    label: str
    target_block_ids: list[str]
    target_node_ids: list[str]
    depends_on: list[str]
    depended_on_by: list[str]
    depth: int
    order_index: int
    suitability: AgentTaskSuitability
    risk: AgentTaskSuitability
    reasons: list[str] = field(default_factory=list)
    ready_to_run: bool = False


@dataclass(slots=True)
class TaskExecutionPlan:
    mode: TaskMode
    items: list[TaskQueueItem]


@dataclass(slots=True)
class TaskUnitPackage:
    item: TaskQueueItem
    related_files: list[str]
    related_blocks: list[str]
    source_snippets: list[str]
    constraints: list[str]
    acceptance_checks: list[str]
    prerequisites: list[str]


@dataclass(slots=True)
class GraphNode:
    id: str
    kind: NodeKind
    label: str
    path: str | None = None
    module: str | None = None
    metadata: dict[str, int | str | bool] = field(default_factory=dict)


@dataclass(slots=True)
class GraphEdge:
    id: str
    source: str
    target: str
    kind: str = "imports"


@dataclass(slots=True)
class FileDetail:
    node_id: str
    path: str
    module: str
    imports: list[ImportRecord]
    classes: list[ClassSummary]
    functions: list[FunctionSummary]
    code_blocks: list[CodeBlockSummary]
    code_block_calls: list[CodeBlockCall]
    symbol_usages: list[SymbolUsage]
    source_preview: str
    syntax_error: str | None = None


@dataclass(slots=True)
class ProjectSummary:
    name: str
    root_path: Path
    python_files: int
    external_packages: int
    parse_duration_ms: int
    parse_errors: int


@dataclass(slots=True)
class ProjectGraph:
    project: ProjectSummary
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    file_details: dict[str, FileDetail]
