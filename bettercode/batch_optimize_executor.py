from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
import json
import re
import time
from typing import Any

from bettercode.models import TaskBatchItem, TaskMode


class BatchRunItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class BatchRunStatus(str, Enum):
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(slots=True)
class BatchRunItemRecord:
    task_id: str
    unit_id: str
    label: str
    phase_index: int
    order_index: int
    status: BatchRunItemStatus
    output_dir: str | None = None
    summary: str = ""
    validation_status: str | None = None
    failure_category: str | None = None
    error: str | None = None
    started_at_ms: int | None = None
    finished_at_ms: int | None = None


@dataclass(slots=True)
class BatchRunReport:
    id: str
    mode: TaskMode
    project_root: str
    scope: str
    selected_phase: int | None
    status: BatchRunStatus
    started_at_ms: int
    finished_at_ms: int | None
    output_dir: str
    items: list[BatchRunItemRecord]


def create_batch_run_report(
    *,
    project_root: Path,
    mode: TaskMode,
    scope: str,
    selected_phase: int | None,
    items: list[TaskBatchItem],
) -> BatchRunReport:
    started_at_ms = _now_ms()
    output_dir = _build_output_directory(
        base_dir=project_root / "generated" / "batch_runs",
        mode=mode,
        scope=scope,
        selected_phase=selected_phase,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    report = BatchRunReport(
        id=output_dir.name,
        mode=mode,
        project_root=str(project_root),
        scope=scope,
        selected_phase=selected_phase,
        status=BatchRunStatus.RUNNING,
        started_at_ms=started_at_ms,
        finished_at_ms=None,
        output_dir=str(output_dir),
        items=[
            BatchRunItemRecord(
                task_id=item.id,
                unit_id=item.unit_id,
                label=item.label,
                phase_index=item.phase_index,
                order_index=item.order_index,
                status=BatchRunItemStatus.PENDING,
            )
            for item in items
        ],
    )
    write_batch_run_report(report)
    return report


def write_batch_run_report(report: BatchRunReport) -> Path:
    path = Path(report.output_dir) / "batch_run_report.json"
    path.write_text(json.dumps(_json_ready(report), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def summarize_batch_run(report: BatchRunReport) -> dict[str, int]:
    counts = {status.value: 0 for status in BatchRunItemStatus}
    for item in report.items:
        counts[item.status.value] = counts.get(item.status.value, 0) + 1
    return counts


def _build_output_directory(*, base_dir: Path, mode: TaskMode, scope: str, selected_phase: int | None) -> Path:
    phase_suffix = f"_phase_{selected_phase}" if selected_phase is not None else ""
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    base_name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{timestamp}_{mode.value}_{scope}{phase_suffix}")
    candidate = base_dir / base_name
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        fallback = base_dir / f"{base_name}_{suffix}"
        if not fallback.exists():
            return fallback
        suffix += 1


def _now_ms() -> int:
    return int(time.time() * 1000)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _json_ready(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_ready(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value
