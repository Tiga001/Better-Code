from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bettercode.optimize_executor import (
    OptimizationApplyResult,
    OptimizationFailureCategory,
    OptimizationResult,
    OptimizationRollbackResult,
    OptimizationStatus,
    OptimizationValidationReport,
    OptimizedFile,
    OriginalFileState,
    ValidationCommandResult,
    ValidationStatus,
)


@dataclass(slots=True)
class OptimizationHistoryEntry:
    task_id: str
    unit_id: str | None
    output_dir: str
    summary: str
    status: OptimizationStatus
    failure_category: OptimizationFailureCategory | None
    validation_status: ValidationStatus
    created_at_ms: int
    changed_files: int
    has_apply_result: bool
    has_rollback_result: bool


def load_optimization_history(project_root: Path) -> dict[str, list[OptimizationHistoryEntry]]:
    history_root = project_root / "generated" / "optimizations"
    if not history_root.is_dir():
        return {}

    entries_by_unit: dict[str, list[OptimizationHistoryEntry]] = {}
    for output_dir in sorted(history_root.iterdir()):
        if not output_dir.is_dir():
            continue
        result_path = output_dir / "optimization_result.json"
        if not result_path.is_file():
            continue
        try:
            result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        task_id, unit_id = _task_identity(output_dir)
        if task_id is None:
            continue
        entry = OptimizationHistoryEntry(
            task_id=task_id,
            unit_id=unit_id,
            output_dir=str(output_dir),
            summary=str(result_payload.get("summary", "")).strip(),
            status=_enum_or_default(OptimizationStatus, result_payload.get("status"), OptimizationStatus.BLOCKED),
            failure_category=_enum_or_none(OptimizationFailureCategory, result_payload.get("failure_category")),
            validation_status=_validation_status_from_payload(result_payload.get("validation_report")),
            created_at_ms=int(result_path.stat().st_mtime * 1000),
            changed_files=len(result_payload.get("changed_files", [])) if isinstance(result_payload.get("changed_files"), list) else 0,
            has_apply_result=(output_dir / "optimization_apply_result.json").is_file(),
            has_rollback_result=(output_dir / "optimization_rollback_result.json").is_file(),
        )
        if unit_id is None:
            continue
        entries_by_unit.setdefault(unit_id, []).append(entry)

    for unit_id, entries in entries_by_unit.items():
        entries.sort(key=lambda item: item.created_at_ms, reverse=True)
    return entries_by_unit


def load_saved_optimization_result(output_dir: Path) -> OptimizationResult:
    payload = json.loads((output_dir / "optimization_result.json").read_text(encoding="utf-8"))
    return OptimizationResult(
        status=_enum_or_default(OptimizationStatus, payload.get("status"), OptimizationStatus.BLOCKED),
        summary=str(payload.get("summary", "")).strip(),
        assumptions=_string_list(payload.get("assumptions")),
        risks=_string_list(payload.get("risks")),
        validation_notes=_string_list(payload.get("validation_notes")),
        suggested_tests=_string_list(payload.get("suggested_tests")),
        changed_files=[
            OptimizedFile(
                path=str(item.get("path", "")),
                content=str(item.get("content", "")),
                purpose=str(item.get("purpose", "")),
            )
            for item in payload.get("changed_files", [])
            if isinstance(item, dict)
        ],
        original_files=[
            OriginalFileState(
                path=str(item.get("path", "")),
                existed_before=bool(item.get("existed_before", False)),
                content=str(item.get("content", "")),
            )
            for item in payload.get("original_files", [])
            if isinstance(item, dict)
        ],
        raw_model_content=str(payload.get("raw_model_content", "")),
        output_dir=str(payload.get("output_dir", str(output_dir))),
        diff_path=str(payload.get("diff_path", str(output_dir / "optimization.patch"))),
        validation_report=_validation_report_from_payload(payload.get("validation_report")),
        raw_model_content_path=str(payload.get("raw_model_content_path")) if payload.get("raw_model_content_path") else None,
        failure_category=_enum_or_none(OptimizationFailureCategory, payload.get("failure_category")),
    )


def load_saved_apply_result(output_dir: Path) -> OptimizationApplyResult | None:
    path = output_dir / "optimization_apply_result.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return OptimizationApplyResult(
        output_dir=str(payload.get("output_dir", str(output_dir))),
        applied_files=_string_list(payload.get("applied_files")),
        validation_report=_validation_report_from_payload(payload.get("validation_report")),
    )


def load_saved_rollback_result(output_dir: Path) -> OptimizationRollbackResult | None:
    path = output_dir / "optimization_rollback_result.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return OptimizationRollbackResult(
        output_dir=str(payload.get("output_dir", str(output_dir))),
        restored_files=_string_list(payload.get("restored_files")),
        validation_report=_validation_report_from_payload(payload.get("validation_report")),
    )


def _task_identity(output_dir: Path) -> tuple[str | None, str | None]:
    package_path = output_dir / "task_unit_package.json"
    if package_path.is_file():
        try:
            payload = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, None
        item = payload.get("item", {})
        if not isinstance(item, dict):
            return None, None
        task_id = str(item.get("id", "")).strip() or None
        unit_id = str(item.get("unit_id", "")).strip() or None
        return task_id, unit_id

    bundle_path = output_dir / "task_bundle.json"
    if bundle_path.is_file():
        try:
            payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, None
        task = payload.get("task", {})
        if not isinstance(task, dict):
            return None, None
        task_id = str(task.get("id", "")).strip() or None
        return task_id, None
    return None, None


def _validation_status_from_payload(payload: Any) -> ValidationStatus:
    if not isinstance(payload, dict):
        return ValidationStatus.BLOCKED
    return _enum_or_default(ValidationStatus, payload.get("status"), ValidationStatus.BLOCKED)


def _validation_report_from_payload(payload: Any) -> OptimizationValidationReport:
    if not isinstance(payload, dict):
        return OptimizationValidationReport(
            status=ValidationStatus.BLOCKED,
            workspace_dir="",
            compile_command=ValidationCommandResult(command="missing", returncode=-1, stdout="", stderr="", ok=False),
            test_command=None,
            notes=[],
        )
    test_command_payload = payload.get("test_command")
    return OptimizationValidationReport(
        status=_enum_or_default(ValidationStatus, payload.get("status"), ValidationStatus.BLOCKED),
        workspace_dir=str(payload.get("workspace_dir", "")),
        compile_command=_command_result_from_payload(payload.get("compile_command")),
        test_command=_command_result_from_payload(test_command_payload) if isinstance(test_command_payload, dict) else None,
        notes=_string_list(payload.get("notes")),
    )


def _command_result_from_payload(payload: Any) -> ValidationCommandResult:
    if not isinstance(payload, dict):
        return ValidationCommandResult(command="missing", returncode=-1, stdout="", stderr="", ok=False)
    return ValidationCommandResult(
        command=str(payload.get("command", "")),
        returncode=int(payload.get("returncode", -1)),
        stdout=str(payload.get("stdout", "")),
        stderr=str(payload.get("stderr", "")),
        ok=bool(payload.get("ok", False)),
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _enum_or_default(enum_type, raw_value: Any, default):
    try:
        return enum_type(str(raw_value))
    except ValueError:
        return default


def _enum_or_none(enum_type, raw_value: Any):
    if raw_value in (None, ""):
        return None
    try:
        return enum_type(str(raw_value))
    except ValueError:
        return None
