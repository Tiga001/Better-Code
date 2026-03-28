# BetterCode Agent API Schema

## Purpose

`analyze_project_for_agent(project_root)` is a side-effect-free Python API that analyzes a Python project and returns agent-oriented JSON. It is intended for external agent loops and subprocess callers, not for the BetterCode UI.

The preferred standalone package is `bettercode_agent_api/`. BetterCode keeps a thin compatibility wrapper at `bettercode.agent_api`.

## Python Entry Point

```python
from bettercode_agent_api import analyze_project_for_agent

result = analyze_project_for_agent("/path/to/python/project")
```

## CLI Entry Point

```bash
python -m bettercode_agent_api /path/to/python/project
```

Compact JSON:

```bash
python -m bettercode_agent_api /path/to/python/project --compact
```

BetterCode also exposes a convenience CLI wrapper:

```bash
bettercode analyze-project /path/to/python/project --compact
```

## Top-Level Contract

The returned object is JSON-serializable and includes these stable top-level fields:

```json
{
  "schema_version": "1.0",
  "analysis_mode": "static",
  "generated_at": "...",
  "project_root": "...",
  "project_name": "...",
  "issues": { ... },
  "dependency_graph": { ... },
  "subsystem_graph": { ... },
  "task_graph": { ... },
  "batch_view": { ... }
}
```

## Top-Level Fields

### `schema_version`
- Stable schema identifier for downstream compatibility.

### `analysis_mode`
- Currently always `"static"`.

### `generated_at`
- ISO-8601 UTC timestamp.

### `project_root`
- Absolute path of the analyzed project root.

### `project_name`
- Basename of `project_root`.

### `issues`

```json
{
  "parse_error_count": 0,
  "syntax_errors": [
    {
      "path": "broken.py",
      "node_id": "file:broken.py",
      "module": "broken",
      "error": "invalid syntax (line 1)"
    }
  ],
  "unresolved_imports": [
    {
      "path": "app.py",
      "node_id": "file:app.py",
      "module": "MissingModule.MissingThing",
      "line": 2
    }
  ],
  "limitations": [
    "Dynamic imports, eval, exec ..."
  ]
}
```

### `dependency_graph`

```json
{
  "project": { ... },
  "nodes": [ ... ],
  "edges": [ ... ],
  "file_details": {
    "pkg/helper.py": { ... }
  },
  "insights": { ... }
}
```

#### `dependency_graph.nodes`
- File nodes and external package nodes.
- Stable file IDs use relative-path form such as `file:pkg/helper.py`.
- External package IDs use `external:<package>`.

#### `dependency_graph.edges`
- File-level import edges.
- `source -> target` means `source` imports `target`.

#### `dependency_graph.file_details[path]`
- Per-file detail indexed by relative path.
- Includes:
  - `node_id`
  - `path`
  - `module`
  - `node_kind`
  - `imports`
  - `classes`
  - `functions`
  - `code_blocks`
  - `code_block_calls`
  - `symbol_usages`
  - `source_preview`
  - `syntax_error`

#### `dependency_graph.insights`
- Graph-level derived data:
  - `cycle_node_ids`
  - `cycle_edge_ids`
  - `isolated_node_ids`
  - `incoming_node_ids`
  - `outgoing_node_ids`
  - `incoming_internal_counts`
  - `outgoing_internal_counts`

### `subsystem_graph`

```json
{
  "subsystems": [
    {
      "id": "subsystem:1",
      "index": 1,
      "node_ids": [ ... ],
      "member_paths": [ ... ],
      "member_nodes": [ ... ],
      "member_edges": [ ... ],
      "entry_node_ids": [ ... ],
      "leaf_node_ids": [ ... ],
      "external_dependency_node_ids": [ ... ]
    }
  ],
  "cross_subsystem_edges": [ ... ]
}
```

Semantics:
- Subsystems are connected components over internal files.
- This is logical subsystem data, not UI layout coordinates.

### `task_graph`

```json
{
  "graph": {
    "units": [ ... ],
    "edges": [ ... ]
  },
  "plans": {
    "optimize": { ... },
    "translate": { ... }
  }
}
```

#### `task_graph.graph.units`
- Task units used for execution planning.
- `kind` is one of:
  - `function`
  - `class_group`
  - `script_block`
  - `cycle_group`

#### `task_graph.graph.edges`
- Includes:
  - `source`
  - `target`
  - `reasons`
  - `dependency_kinds`
  - `is_blocking`

`dependency_kinds` currently distinguishes:
- `strong_call`
- `inheritance`
- `import_only`

#### `task_graph.plans.optimize|translate`
- Ordered execution plan for a mode.
- Contains `items`, each with:
  - `id`
  - `unit_id`
  - `mode`
  - `label`
  - `target_block_ids`
  - `target_node_ids`
  - `depends_on`
  - `depended_on_by`
  - `depth`
  - `order_index`
  - `suitability`
  - `risk`
  - `context_depends_on`
  - `context_depended_on_by`
  - `reasons`
  - `ready_to_run`

### `batch_view`

```json
{
  "optimize": {
    "mode": "optimize",
    "items": [ ... ],
    "phases": [ ... ]
  },
  "translate": {
    "mode": "translate",
    "items": [ ... ],
    "phases": [ ... ]
  }
}
```

Semantics:
- Batch view is an execution projection of task planning.
- It groups tasks into phase-indexed execution layers.

#### `batch_view.<mode>.items`
- Batch items include:
  - `id`
  - `unit_id`
  - `mode`
  - `label`
  - `phase_index`
  - `order_index`
  - `target_block_ids`
  - `target_node_ids`
  - `blocking_dependencies`
  - `context_dependencies`
  - `suitability`
  - `risk`
  - `reasons`
  - `ready_to_run`

#### `batch_view.<mode>.phases`
- Array of:
  - `index`
  - `item_ids`

## Stability Guarantees

The following are intended to be stable protocol elements for external agent consumers:
- Top-level field names listed above
- Relative-path file IDs such as `file:pkg/helper.py`
- External package IDs such as `external:requests`
- Task unit IDs such as `task_unit:file:...`
- `dependency_kinds`
- `batch_view` phase structure

## Analysis Boundaries

This API is intentionally static-analysis-first.

Known limitations:
- Dynamic imports are not precisely resolved.
- `eval`, `exec`, reflection, monkey patching, and runtime-only dispatch are not modeled precisely.
- Task and batch outputs are planning structures, not proof of runtime behavior.
- No UI coordinates are returned.

## Directory Ignore Defaults

The analyzer ignores these by default:
- `.git`
- `.venv`
- `venv`
- `__pycache__`
- `build`
- `dist`
- `generated`
- `node_modules`

## Intended Usage

This API is intended for:
- external agent loops
- task planning tools
- codebase orchestration workflows
- offline analysis pipelines

It is not intended to trigger optimization or translation execution directly.
