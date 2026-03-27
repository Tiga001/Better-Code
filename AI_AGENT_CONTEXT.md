# BetterCode AI Agent Context

This file is for AI coding agents, not for end-user documentation.
Assume the reader needs fast repository activation, accurate architectural context, and current implementation boundaries.

## 0. Project Identity

- Project name: `BetterCode`
- Root path: `/Users/shenhuajiao/PycharmProjects/BetterCode`
- Product type: pure Python desktop application
- UI stack: `PySide6`
- Primary goal: Python codebase understanding + task decomposition + ordered execution + AI-assisted optimization workflow
- Secondary / experimental goal: code translation (`Python -> C++`)

This is **not** just a dependency graph viewer.
Current mainline is:

1. import project
2. parse graph + code blocks
3. generate task graph and phase batches
4. run single-task optimization with preview / validation / apply / rollback
5. run batch optimization in phase order with monitoring

## 1. Current Status Snapshot

Known-good local regression at time of writing:

- command: `python3 -m unittest discover -s tests`
- result: `Ran 100 tests ... OK`

Current working tree status at time of writing:

- untracked packaging-related files exist:
  - `.github/`
  - `BetterCode.spec`
  - `scripts/`
- untracked mac finder artifact:
  - `.DS_Store`

Interpretation:

- the core application and tests are green
- packaging scaffolding exists locally but may not yet be committed

## 2. Core Runtime Entry Points

- top-level launcher: `/Users/shenhuajiao/PycharmProjects/BetterCode/app.py`
- app bootstrap: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/app.py`
- main window: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/main_window.py`

Main window owns:

- project loading
- canvas mode switching
- selection synchronization
- model config entry
- single-task optimize / translate actions
- batch execution loop
- optimization history reopening

## 3. High-Level Architecture

### 3.1 Parsing and analysis layer

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/parser.py`
  - scans Python projects
  - builds file graph
  - extracts code blocks
  - resolves imports
  - resolves part of cross-file calls/usages
  - supports module-scope script blocks
  - ignores common build/cache dirs and `generated/`

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/graph_analysis.py`
  - cycle detection
  - isolated file detection
  - subsystem decomposition (connected components over internal graph)

### 3.2 Task planning layer

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/task_planner.py`
  - task candidates for `optimize` and `translate`
  - task bundle construction

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/task_graph.py`
  - converts code blocks into task units
  - builds task DAG
  - separates blocking dependencies vs context-only dependencies
  - builds phase batches
  - builds `TaskUnitPackage`

Important design decision:

- analysis granularity can stay below class level
- execution granularity for `CLASS_GROUP` is currently **class block**
- class methods are analysis context, not separate editable targets inside one class-group optimization package

### 3.3 Execution layer

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/optimize_executor.py`
  - single-task optimize flow
  - model request construction
  - structured `edits[]` protocol
  - local application of edits
  - pre-validation
  - apply / rollback

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/translation_executor.py`
  - experimental translation executor
  - generates artifacts under `generated/translations/`
  - does not yet provide full compile / equivalence verification

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/batch_optimize_executor.py`
  - batch run report datamodel
  - batch output directories
  - report serialization

### 3.4 UI layer

Primary canvases:

- dependency graph: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/graph_view.py`
- subsystem view: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/subsystem_view.py`
- task graph: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/task_graph_view.py`
- batch / phase view: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/task_batch_view.py`

Auxiliary panels/dialogs:

- file detail: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/detail_panel.py`
- task detail: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/task_detail_panel.py`
- batch monitor: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/batch_monitor_panel.py`
- code block dialog: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/code_block_dialog.py`
- optimization review dialog: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/optimization_review_dialog.py`
- batch run report dialog: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/batch_run_report_dialog.py`
- model config dialog: `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/model_config_dialog.py`

Export helper:

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/scene_export.py`

Localization:

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/i18n.py`

## 4. Important Domain Objects

Defined in:

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/models.py`

Important categories:

- file graph:
  - `ProjectGraph`
  - `GraphNode`
  - `GraphEdge`
  - `FileDetail`

- code blocks:
  - `CodeBlock`
  - `CodeBlockKind`

- task planning:
  - `TaskCandidate`
  - `TaskBundle`
  - `TaskTargetBlock`

- task graph / queue:
  - `TaskGraphUnit`
  - `TaskGraphEdge`
  - `TaskQueueItem`
  - `TaskExecutionPlan`
  - `TaskBatchItem`
  - `TaskBatchPhase`
  - `TaskBatch`
  - `TaskUnitPackage`

Do not invent parallel structures unless necessary. The repository already has a stable task data model.

## 5. Current Product Semantics

### 5.1 Graph modes

Four primary graph modes exist:

1. `dependency`
2. `subsystems`
3. `tasks`
4. `batches`

Expected role split:

- dependency graph: inspect project/file structure
- subsystem graph: inspect connected internal clusters
- task graph: inspect and assign single task units
- batch view: monitor phase execution and review batch-level results

Batch view right panel should remain batch-level, not single-task-detail-first.

### 5.2 File node types

Main categories in dependency/subsystem graphs:

- external package
- dependency leaf
- internal file
- top-level script

`__init__.py` participates in dependency analysis but should not be misclassified as a reusable leaf.

### 5.3 Task unit types

- function task
- class group
- script block task
- cycle group

### 5.4 Batch execution semantics

Current batch behavior:

- optimize mode only
- serial execution
- by phase order
- any failed/non-passed task blocks later pending tasks
- UI shows running/passed/failed/blocked states
- batch monitor panel shows completed and issue history with diff reopening

This is execution monitoring, not a full production-grade orchestration system yet.

## 6. Optimization Flow: Actual Current Behavior

Single-task optimize flow:

1. build `TaskUnitPackage`
2. build model request
3. send request to chat-completions style endpoint
4. expect structured `edits[]` response (preferred)
5. locally apply edits to full file content
6. build candidate files + unified diff
7. run preview validation in isolated workspace
8. open review dialog
9. user may apply patch to live workspace
10. user may rollback
11. history saved under `generated/optimizations/...`

Important:

- current protocol prefers `edits[]`, not whole-file rewrites
- legacy `changed_files[].content` compatibility still exists
- safety checks intentionally block destructive or ambiguous edits

### 6.1 Safety checks already present

`/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/optimize_executor.py`

Examples:

- invalid model JSON -> `bad_model_output`
- destructive top-level definition removal -> `safety_blocked`
- validation failure -> `validation_failed`
- overlapping structured edits -> blocked
- edit target mismatch -> blocked
- method/module_scope indentation normalization exists for edit matching and write-back

## 7. Validation Reality

Do not overstate validation maturity.

Current validation is a **basic safety net**:

- preview validation:
  - `python3 -m compileall .`
  - `python3 -m unittest discover -s tests` if `tests/` exists
- apply validation:
  - same checks again in live workspace
- rollback validation:
  - same checks again after restore

Validation gaps are intentionally documented in:

- `/Users/shenhuajiao/PycharmProjects/BetterCode/VALIDATION_GAPS.md`

Agents should read that file before proposing “strict correctness” claims.

## 8. Optimization / Translation History and Generated Artifacts

Generated outputs are intentionally kept outside source flow:

- `generated/optimizations/`
- `generated/translations/`
- `generated/batch_runs/`

History loader:

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/optimization_history.py`

Batch monitor and task detail panels both reopen history via saved result directories.

Do not treat `generated/` as source tree input. Parser now ignores `generated/` on purpose.

## 9. Model Configuration and Sensitive Data

Model config storage:

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/model_config_store.py`

User-facing config UI:

- `/Users/shenhuajiao/PycharmProjects/BetterCode/bettercode/ui/model_config_dialog.py`

Important:

- API tokens must never be committed
- local model/API settings are not supposed to live in git
- repository may include placeholder strings like `"token"` in tests; those are not secrets

If adding logs/debugging, do not write real tokens into repository files.

## 10. Packaging Status

Packaging work exists locally:

- spec: `/Users/shenhuajiao/PycharmProjects/BetterCode/BetterCode.spec`
- build script: `/Users/shenhuajiao/PycharmProjects/BetterCode/scripts/build_desktop.py`
- GitHub Actions workflow scaffold: `/Users/shenhuajiao/PycharmProjects/BetterCode/.github/workflows/build-desktop.yml`

Known local outcome:

- mac build path produced:
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/dist/BetterCode.app`

Windows `.exe` is not produced locally on macOS; workflow scaffold is intended for Windows runners.

At time of writing these packaging files are local/untracked unless later committed.

## 11. Test Suite Map

Representative test files:

- parser:
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_parser.py`

- graph analysis:
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_graph_analysis.py`

- dependency graph UI:
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_graph_view_selection.py`
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_graph_view_labels.py`

- subsystem UI:
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_subsystem_view.py`

- task graph / batch UI:
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_task_graph.py`
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_task_graph_view.py`
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_task_batch_view.py`
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_task_detail_panel.py`
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_main_window_i18n.py`

- executor layer:
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_optimize_executor.py`
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_optimization_review_dialog.py`
  - `/Users/shenhuajiao/PycharmProjects/BetterCode/tests/test_translation_executor.py`

Agents should extend the closest test file instead of creating random new test locations.

## 12. High-Risk Areas

If changing these, read the existing code first:

1. `parser.py`
   - import resolution
   - star imports
   - module-scope block extraction
   - internal vs external package classification

2. `task_graph.py`
   - class-group granularity
   - blocking vs context dependency semantics
   - phase generation

3. `optimize_executor.py`
   - structured edit protocol
   - model response parsing
   - safety gates
   - preview/apply/rollback invariants

4. `main_window.py`
   - view mode switching
   - selection synchronization
   - batch worker thread lifecycle
   - reopening optimization history

5. `task_batch_view.py` / `batch_monitor_panel.py`
   - batch execution controls
   - current mode switching
   - running state UI

## 13. Known Open Product Gaps

These are not bugs unless the task explicitly targets them:

- validation is not strict enough yet
- translation lacks end-to-end verification
- dynamic Python behavior is only partially modeled
- batch execution is serial and optimize-only
- no true agent orchestration layer yet
- no project-specific validation command configuration yet

## 14. Recommended Development Heuristics For New Agents

1. Do not add new abstractions if an existing dataclass/model already fits.
2. Prefer improving the current task / batch / optimization pipeline over adding new UI chrome.
3. Preserve the role split between:
   - code-block analysis
   - task execution
   - batch monitoring
4. Be conservative around optimization safety checks.
5. Avoid claiming semantic correctness unless validation work actually supports it.
6. When touching UI mode behavior, update `tests/test_main_window_i18n.py`.
7. When touching parser/task graph semantics, update parser/task graph tests.
8. Treat generated artifacts as outputs, not source inputs.

## 15. Fast Start Commands For Agents

```bash
cd /Users/shenhuajiao/PycharmProjects/BetterCode
python3 -m unittest discover -s tests
python3 app.py
```

Optional packaging command:

```bash
python3 scripts/build_desktop.py
```

## 16. If You Need One-Line Intent

BetterCode is a Python-first code operations workbench: parse the repo, decompose it into ordered tasks, let AI propose changes safely, then preview/validate/apply/rollback those changes with a UI that exposes the graph and execution state.
