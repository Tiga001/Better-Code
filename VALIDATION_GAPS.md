# BetterCode Validation Gaps

## Purpose

This note records the current gaps in BetterCode's automated validation pipeline.
It is intentionally separated from the active feature roadmap so validation can be revisited later as a focused track.

## Current Validation Baseline

The current optimization workflow validates in three stages:

1. Preview validation
   - Copy the project into a temporary validation workspace
   - Overlay candidate files
   - Run `python3 -m compileall .`
   - If `tests/` exists, run `python3 -m unittest discover -s tests`

2. Apply validation
   - Write candidate files into the live workspace
   - Run the same validation commands again

3. Rollback validation
   - Restore original files
   - Run the same validation commands again

This gives BetterCode a basic safety net, but not a complete proof of correctness.

## Main Gaps

### 1. Validation commands are too generic

Current behavior is hard-coded to:

- `python3 -m compileall .`
- `python3 -m unittest discover -s tests`

Problems:

- Many real projects use `pytest`, `tox`, `nox`, `make test`, custom scripts, or app-specific smoke tests.
- Some projects have no `tests/` directory but still have a valid validation command.
- Some repositories need environment setup before tests can run.

Impact:

- BetterCode may report a weak pass on a project that has not been meaningfully validated.

### 2. No semantic or behavior-preservation check

Current validation mostly proves:

- syntax is valid
- some tests passed

It does **not** prove:

- function behavior stayed the same
- object state transitions stayed the same
- UI behavior stayed the same
- output contracts stayed the same

Impact:

- A change can be "green" while still being behaviorally wrong.

### 3. No interface compatibility check

Current validation does not explicitly verify that public APIs remain stable.

Missing checks:

- function signatures
- method signatures
- exported classes/functions
- expected module-level names

Impact:

- A refactor can silently break callers even if local compile/test checks pass.

### 4. No coverage-awareness

Current validation does not know whether changed code is actually covered by tests.

Missing checks:

- whether modified lines are executed by tests
- whether modified tasks affect high fan-in symbols with low coverage

Impact:

- A passing test run may still be weak evidence.

### 5. No runtime dependency tracing

Current project analysis is mostly static.

Known blind spots:

- `eval`
- `exec`
- `getattr` / `setattr`
- dynamic import
- plugin registration
- monkey patching

Impact:

- Task ordering and validation confidence are both limited for dynamic Python code.

### 6. No project-specific smoke validation

For many Python applications, the meaningful validation is not unit tests alone.

Missing examples:

- import startup smoke tests
- CLI entrypoint checks
- GUI window construction smoke tests
- service boot checks

Impact:

- Changes can break actual usage paths while still passing compile/test basics.

### 7. No strict validation tier

Current validation is effectively one level.

BetterCode does not yet distinguish:

- basic pass
- strict pass
- pass with limited evidence

Impact:

- The system cannot clearly say whether a result is "safe enough to trust" or merely "did not fail obvious checks."

### 8. No task-level behavioral probes

BetterCode can target a function, class, or script block, but validation is still repository-level.

Missing checks:

- task-scoped input/output comparison
- before/after sample execution for the target block
- class-level behavior probes

Impact:

- Validation is not yet aligned with the granularity of task execution.

### 9. No translation verification loop

Translation mode is not yet validated end-to-end.

Missing pieces:

- generated `CMake` project verification
- compile/link verification
- Python/C++ equivalence tests
- dependency mapping validation

Impact:

- Translation output is currently candidate generation, not trustworthy migration.

### 10. No batch-level validation policy

Single-task validation exists, but batch execution still lacks a complete validation policy.

Missing pieces:

- phase-level stop conditions
- per-task validation escalation rules
- partial batch failure handling
- batch report confidence scoring

Impact:

- Batch execution cannot yet be considered production-grade.

## Recommended Future Work

### Phase A: Practical validation upgrades

- Support user-configurable validation commands
- Support multiple command slots:
  - build/syntax
  - test
  - smoke
- Persist validation config per project

### Phase B: Structural validation

- Add AST-based API compatibility checks
- Detect signature drift
- Detect removed exported symbols

### Phase C: Behavioral validation

- Add task-level before/after probes
- Support user-defined sample inputs
- Record expected outputs when available

### Phase D: Confidence model

- Introduce validation grades:
  - `passed_basic`
  - `passed_strict`
  - `needs_review`
  - `blocked`
- Base the grade on:
  - structural checks
  - test results
  - task coverage
  - runtime confidence

### Phase E: Runtime augmentation

- Add optional runtime tracing during tests
- Merge static and runtime dependency evidence
- Mark dynamic-only edges separately

## Suggested Future Question

When validation work resumes, the first design question should be:

> What should count as a strict pass for BetterCode: syntax + project tests, or syntax + project tests + task-level behavior equivalence?

## Status

Deferred for later discussion.
