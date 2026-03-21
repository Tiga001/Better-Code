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
