from __future__ import annotations

import ast
import difflib
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

from bettercode.llm.gateway import LLMGatewayError, request_chat_completion
from bettercode.models import CodeBlockKind, TaskBundle, TaskMode, TaskTargetBlock, TaskUnitPackage
from bettercode.task_graph import task_unit_package_to_dict
from bettercode.task_planner import task_bundle_to_dict
from bettercode.translation_executor import ModelConfig, TranslationConfigError


class OptimizationStatus(str, Enum):
    OPTIMIZED = "optimized"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    BLOCKED = "blocked"


class OptimizationFailureCategory(str, Enum):
    BAD_MODEL_OUTPUT = "bad_model_output"
    SAFETY_BLOCKED = "safety_blocked"
    VALIDATION_FAILED = "validation_failed"


class OptimizationEditKind(str, Enum):
    REPLACE_BLOCK = "replace_block"


class ValidationStatus(str, Enum):
    PASSED = "passed"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"


@dataclass(slots=True)
class OptimizedFile:
    path: str
    content: str
    purpose: str


@dataclass(slots=True)
class OriginalFileState:
    path: str
    existed_before: bool
    content: str


@dataclass(slots=True)
class OptimizationEdit:
    path: str
    kind: OptimizationEditKind
    target_block_id: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    old_text: str | None = None
    new_text: str = ""
    purpose: str = ""


@dataclass(slots=True)
class ValidationCommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    ok: bool


@dataclass(slots=True)
class OptimizationValidationReport:
    status: ValidationStatus
    workspace_dir: str
    compile_command: ValidationCommandResult
    test_command: ValidationCommandResult | None
    notes: list[str]


@dataclass(slots=True)
class OptimizationRequest:
    system_prompt: str
    user_payload: dict[str, Any]
    api_payload: dict[str, Any]


@dataclass(slots=True)
class OptimizationResult:
    status: OptimizationStatus
    summary: str
    assumptions: list[str]
    risks: list[str]
    validation_notes: list[str]
    suggested_tests: list[str]
    changed_files: list[OptimizedFile]
    original_files: list[OriginalFileState]
    raw_model_content: str
    output_dir: str
    diff_path: str
    validation_report: OptimizationValidationReport
    edits: list[OptimizationEdit] = field(default_factory=list)
    raw_model_content_path: str | None = None
    failure_category: OptimizationFailureCategory | None = None


@dataclass(slots=True)
class OptimizationApplyResult:
    output_dir: str
    applied_files: list[str]
    validation_report: OptimizationValidationReport


@dataclass(slots=True)
class OptimizationRollbackResult:
    output_dir: str
    restored_files: list[str]
    validation_report: OptimizationValidationReport


class OptimizationExecutionError(RuntimeError):
    pass


class OptimizationConfigError(OptimizationExecutionError):
    pass


OptimizationPayload = TaskBundle | TaskUnitPackage


def execute_optimization(
    bundle: OptimizationPayload,
    *,
    project_root: Path,
    output_root: Path | None = None,
    config: ModelConfig | None = None,
) -> OptimizationResult:
    if _payload_mode(bundle) is not TaskMode.OPTIMIZE:
        raise OptimizationExecutionError("Optimize executor only accepts optimize task packages.")

    try:
        model_config = config or ModelConfig.from_env()
    except TranslationConfigError as error:
        raise OptimizationConfigError(str(error)) from error

    request_payload = build_optimization_request(bundle, project_root=project_root, config=model_config)
    destination = _build_output_directory(
        base_dir=output_root or (project_root / "generated" / "optimizations"),
        task_id=_payload_id(bundle),
    )
    destination.mkdir(parents=True, exist_ok=True)
    diff_path = destination / "optimization.patch"
    diff_path.write_text("", encoding="utf-8")

    _write_json(destination / _payload_snapshot_name(bundle), _payload_to_dict(bundle))
    _write_json(
        destination / "optimization_request.json",
        {
            "system_prompt": request_payload.system_prompt,
            "user_payload": request_payload.user_payload,
            "api_payload": request_payload.api_payload,
        },
    )

    raw_model_content = ""
    raw_model_content_path: str | None = None
    failure_category: OptimizationFailureCategory | None = None
    parse_retry_notes: list[str] = []
    parsed_result: dict[str, Any] | None = None

    for attempt in (1, 2):
        response_payload = _post_model_request(
            api_url=model_config.api_url,
            api_token=model_config.api_token,
            api_payload=request_payload.api_payload,
            timeout_seconds=model_config.timeout_seconds,
        )
        _write_json(destination / f"optimization_response_attempt_{attempt}.json", response_payload)
        raw_model_content = _extract_message_content(response_payload)
        raw_path = destination / f"raw_model_content_attempt_{attempt}.txt"
        raw_path.write_text(raw_model_content, encoding="utf-8")
        try:
            parsed_result = _parse_model_result(raw_model_content)
            raw_model_content_path = str(destination / "raw_model_content.txt")
            _write_json(destination / "optimization_response.json", response_payload)
            Path(raw_model_content_path).write_text(raw_model_content, encoding="utf-8")
            if attempt > 1:
                parse_retry_notes.append("The first model response was invalid JSON; retry attempt succeeded.")
            break
        except OptimizationExecutionError as error:
            parse_retry_notes.append(f"Attempt {attempt} returned invalid model output: {error}")
            if attempt == 2:
                raw_model_content_path = str(destination / "raw_model_content.txt")
                _write_json(destination / "optimization_response.json", response_payload)
                Path(raw_model_content_path).write_text(raw_model_content, encoding="utf-8")
                failure_category = OptimizationFailureCategory.BAD_MODEL_OUTPUT
                validation_report = _build_skipped_validation_report(
                    workspace_dir=destination,
                    notes=[
                        "Optimization validation did not run because the model returned invalid JSON twice.",
                        *parse_retry_notes,
                    ],
                    status=ValidationStatus.BLOCKED,
                )
                result = OptimizationResult(
                    status=OptimizationStatus.BLOCKED,
                    summary="The model returned invalid JSON twice, so the optimization result was blocked.",
                    assumptions=[],
                    risks=list(parse_retry_notes),
                    validation_notes=list(parse_retry_notes),
                    suggested_tests=[],
                    changed_files=[],
                    original_files=[],
                    raw_model_content=raw_model_content,
                    output_dir=str(destination),
                    diff_path=str(diff_path),
                    validation_report=validation_report,
                    raw_model_content_path=raw_model_content_path,
                    failure_category=failure_category,
                )
                _write_json(destination / "validation_report.json", _json_ready(validation_report))
                _write_json(destination / "optimization_result.json", _json_ready(result))
                return result

    if parsed_result is None:
        raise OptimizationExecutionError("Optimization parsing failed without a recoverable result.")

    changed_files: list[OptimizedFile]
    try:
        edits = _edits_from_payload(parsed_result)
        if edits:
            changed_files = _changed_files_from_edits(
                bundle=bundle,
                project_root=project_root,
                edits=edits,
            )
        else:
            changed_files = _changed_files_from_payload(parsed_result)
    except OptimizationExecutionError as error:
        edits = []
        changed_files = []
        parsed_result["status"] = OptimizationStatus.BLOCKED.value
        parsed_result["summary"] = (
            "Rejected the optimization candidate because the returned edit plan was unsafe or out of scope."
        )
        parsed_result["risks"] = [str(error), *_string_list(parsed_result.get("risks"))]
        parsed_result["validation_notes"] = [str(error), *_string_list(parsed_result.get("validation_notes"))]
        failure_category = OptimizationFailureCategory.SAFETY_BLOCKED
    safety_violations = _candidate_safety_violations(
        bundle=bundle,
        project_root=project_root,
        changed_files=changed_files,
    )
    if safety_violations:
        changed_files = []
        parsed_result["status"] = OptimizationStatus.BLOCKED.value
        parsed_result["summary"] = (
            "Rejected the optimization candidate because safety checks detected destructive or out-of-scope edits."
        )
        parsed_result["risks"] = [*safety_violations, *_string_list(parsed_result.get("risks"))]
        parsed_result["validation_notes"] = [*safety_violations, *_string_list(parsed_result.get("validation_notes"))]
        failure_category = OptimizationFailureCategory.SAFETY_BLOCKED
    original_files = _capture_original_files(
        project_root=project_root,
        changed_files=changed_files,
        output_dir=destination,
    )

    candidate_root = destination / "candidate_files"
    for changed_file in changed_files:
        output_path = _safe_generated_path(candidate_root, changed_file.path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(changed_file.content, encoding="utf-8")

    diff_text = _build_unified_diff(project_root=project_root, changed_files=changed_files)
    diff_path.write_text(diff_text, encoding="utf-8")

    validation_report = build_preview_validation_report(
        project_root=project_root,
        changed_files=changed_files,
        output_dir=destination,
        validation_notes=[*parse_retry_notes, *_string_list(parsed_result.get("validation_notes"))],
        suggested_tests=_string_list(parsed_result.get("suggested_tests")),
    )
    status = _optimization_status_from_payload(parsed_result)
    if validation_report.status is not ValidationStatus.PASSED and failure_category is None:
        failure_category = OptimizationFailureCategory.VALIDATION_FAILED
        if status is OptimizationStatus.OPTIMIZED:
            status = (
                OptimizationStatus.BLOCKED
                if validation_report.status is ValidationStatus.BLOCKED
                else OptimizationStatus.NEEDS_MANUAL_REVIEW
            )
    result = OptimizationResult(
        status=status,
        summary=str(parsed_result.get("summary", "")).strip() or "No summary returned.",
        assumptions=_string_list(parsed_result.get("assumptions")),
        risks=_string_list(parsed_result.get("risks")),
        validation_notes=[*parse_retry_notes, *_string_list(parsed_result.get("validation_notes"))],
        suggested_tests=_string_list(parsed_result.get("suggested_tests")),
        changed_files=changed_files,
        original_files=original_files,
        raw_model_content=raw_model_content,
        output_dir=str(destination),
        diff_path=str(diff_path),
        validation_report=validation_report,
        edits=edits,
        raw_model_content_path=raw_model_content_path,
        failure_category=failure_category,
    )
    _write_json(destination / "validation_report.json", _json_ready(validation_report))
    _write_json(destination / "optimization_result.json", _json_ready(result))
    return result


def build_optimization_request(
    bundle: OptimizationPayload,
    *,
    project_root: Path,
    config: ModelConfig,
) -> OptimizationRequest:
    if _payload_mode(bundle) is not TaskMode.OPTIMIZE:
        raise OptimizationExecutionError("Only optimize task packages can be sent to the optimization model.")

    editable_files = _build_request_files(project_root=project_root, relative_paths=_payload_editable_files(bundle))
    context_files = _build_request_files(project_root=project_root, relative_paths=_payload_context_files(bundle))
    system_prompt = (
        "You are a senior Python refactoring engineer. "
        "Optimize exactly one Python task package while preserving behavior and public interfaces. "
        "You do not have filesystem access beyond the files included in this request. "
        "Only edit files listed under editable_files. Treat context_files as read-only reference. "
        "Preserve unrelated top-level definitions, imports, and file structure unless a change is strictly required "
        "for the target task. "
        "Return only valid JSON, with no markdown fences. "
        "Prefer structured edits over full rewritten files. "
        "Each edit must target a provided target_block_id and must not overlap another edit. "
        "Use replace_block edits for local refactors. "
        "Use this JSON schema: "
        '{"status":"optimized|needs_manual_review|blocked",'
        '"summary":"...",'
        '"assumptions":["..."],'
        '"risks":["..."],'
        '"validation_notes":["..."],'
        '"suggested_tests":["..."],'
        '"edits":[{"path":"relative/path.py","kind":"replace_block","target_block_id":"block-id","start_line":1,"end_line":2,"old_text":"existing block text","new_text":"updated block text","purpose":"short description"}],'
        '"changed_files":[{"path":"relative/path.py","purpose":"deprecated fallback","content":"full file content"}]}'
    )
    user_payload = {
        _payload_request_key(bundle): _payload_to_dict(bundle),
        "target_blocks": [_json_ready(block) for block in _payload_target_blocks(bundle)],
        "editable_files": editable_files,
        "context_files": context_files,
        "optimization_constraints": {
            "source_language": "python",
            "write_back_policy": "generated_only",
            "preserve_behavior": True,
            "preserve_public_interfaces": True,
            "prefer_local_changes": True,
            "editable_files_only": True,
        },
        "rules": [
            "Return edits instead of full rewritten files whenever possible.",
            "Prefer one non-overlapping replace_block edit per target block that truly needs a change.",
            "Never invent or assume unseen file content.",
            "Only use paths that appear in editable_files.",
            "Only reference target_block_id values that appear in target_blocks.",
            "Do not delete unrelated top-level classes or functions from editable files.",
            "Prefer smaller, behavior-preserving refactors over broad rewrites.",
            "Keep imports and surrounding file structure stable unless a cleanup is required.",
            "Do not introduce new third-party dependencies.",
        ],
    }
    api_payload = {
        "stream": False,
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
        ],
    }
    return OptimizationRequest(system_prompt=system_prompt, user_payload=user_payload, api_payload=api_payload)


def apply_optimization_result(
    result: OptimizationResult,
    *,
    project_root: Path,
) -> OptimizationApplyResult:
    output_dir = Path(result.output_dir)
    _assert_workspace_matches_original(project_root=project_root, original_files=result.original_files)

    for changed_file in result.changed_files:
        target_path = _safe_generated_path(project_root, changed_file.path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(changed_file.content, encoding="utf-8")

    validation_report = build_live_validation_report(
        project_root=project_root,
        output_dir=output_dir,
        validation_notes=[
            "Validation ran against the live workspace after applying the optimization patch.",
            *result.validation_notes,
        ],
        suggested_tests=result.suggested_tests,
        file_name="apply_validation_report.json",
    )
    apply_result = OptimizationApplyResult(
        output_dir=str(output_dir),
        applied_files=[changed_file.path for changed_file in result.changed_files],
        validation_report=validation_report,
    )
    _write_json(output_dir / "optimization_apply_result.json", _json_ready(apply_result))
    return apply_result


def rollback_optimization_result(
    result: OptimizationResult,
    *,
    project_root: Path,
) -> OptimizationRollbackResult:
    output_dir = Path(result.output_dir)
    _assert_workspace_matches_candidate(project_root=project_root, changed_files=result.changed_files)

    restored_files: list[str] = []
    for original_file in result.original_files:
        target_path = _safe_generated_path(project_root, original_file.path)
        if original_file.existed_before:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(original_file.content, encoding="utf-8")
        elif target_path.exists():
            target_path.unlink()
        restored_files.append(original_file.path)

    validation_report = build_live_validation_report(
        project_root=project_root,
        output_dir=output_dir,
        validation_notes=["Validation ran against the live workspace after rollback restored the original files."],
        suggested_tests=result.suggested_tests,
        file_name="rollback_validation_report.json",
    )
    rollback_result = OptimizationRollbackResult(
        output_dir=str(output_dir),
        restored_files=restored_files,
        validation_report=validation_report,
    )
    _write_json(output_dir / "optimization_rollback_result.json", _json_ready(rollback_result))
    return rollback_result


def build_preview_validation_report(
    *,
    project_root: Path,
    changed_files: list[OptimizedFile],
    output_dir: Path,
    validation_notes: list[str],
    suggested_tests: list[str],
) -> OptimizationValidationReport:
    workspace_dir = output_dir / "validation_workspace"
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    shutil.copytree(
        project_root,
        workspace_dir,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            "generated",
            "build",
            "dist",
            ".pytest_cache",
            "*.pyc",
        ),
    )

    for changed_file in changed_files:
        workspace_path = _safe_generated_path(workspace_dir, changed_file.path)
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        workspace_path.write_text(changed_file.content, encoding="utf-8")

    return _run_validation_commands(
        workspace_dir=workspace_dir,
        validation_notes=[
            "Validation ran against a copied workspace with generated candidate files overlaid.",
            *validation_notes,
        ],
        suggested_tests=suggested_tests,
    )


def build_live_validation_report(
    *,
    project_root: Path,
    output_dir: Path,
    validation_notes: list[str],
    suggested_tests: list[str],
    file_name: str,
) -> OptimizationValidationReport:
    report = _run_validation_commands(
        workspace_dir=project_root,
        validation_notes=validation_notes,
        suggested_tests=suggested_tests,
    )
    _write_json(output_dir / file_name, _json_ready(report))
    return report


def _build_skipped_validation_report(
    *,
    workspace_dir: Path,
    notes: list[str],
    status: ValidationStatus,
) -> OptimizationValidationReport:
    return OptimizationValidationReport(
        status=status,
        workspace_dir=str(workspace_dir),
        compile_command=ValidationCommandResult(
            command="skipped",
            returncode=-1,
            stdout="",
            stderr="Validation was skipped.",
            ok=False,
        ),
        test_command=None,
        notes=notes,
    )


def _build_output_directory(*, base_dir: Path, task_id: str) -> Path:
    safe_task_id = re.sub(r"[^A-Za-z0-9._-]+", "_", task_id).strip("._") or "optimization_task"
    candidate = base_dir / safe_task_id
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        fallback = base_dir / f"{safe_task_id}_{suffix}"
        if not fallback.exists():
            return fallback
        suffix += 1


def _payload_mode(bundle: OptimizationPayload) -> TaskMode:
    if isinstance(bundle, TaskBundle):
        return bundle.task.mode
    return bundle.item.mode


def _payload_id(bundle: OptimizationPayload) -> str:
    if isinstance(bundle, TaskBundle):
        return bundle.task.id
    return bundle.item.id


def _payload_request_key(bundle: OptimizationPayload) -> str:
    return "task_bundle" if isinstance(bundle, TaskBundle) else "task_unit_package"


def _payload_snapshot_name(bundle: OptimizationPayload) -> str:
    return "task_bundle.json" if isinstance(bundle, TaskBundle) else "task_unit_package.json"


def _payload_to_dict(bundle: OptimizationPayload) -> dict[str, Any]:
    if isinstance(bundle, TaskBundle):
        return task_bundle_to_dict(bundle)
    return task_unit_package_to_dict(bundle)


def _payload_editable_files(bundle: OptimizationPayload) -> list[str]:
    editable_files = getattr(bundle, "editable_files", None)
    if isinstance(editable_files, list) and editable_files:
        return [str(path) for path in editable_files if str(path).strip()]
    if isinstance(bundle, TaskBundle):
        target_path = _node_id_to_path(bundle.task.target_node_id)
        return [target_path] if target_path else list(bundle.related_files[:1])
    return list(bundle.related_files)


def _payload_context_files(bundle: OptimizationPayload) -> list[str]:
    context_files = getattr(bundle, "context_files", None)
    if isinstance(context_files, list):
        return [str(path) for path in context_files if str(path).strip()]
    editable = set(_payload_editable_files(bundle))
    if isinstance(bundle, TaskBundle):
        return [path for path in bundle.related_files if path not in editable]
    return []


def _payload_target_blocks(bundle: OptimizationPayload) -> list[TaskTargetBlock]:
    target_blocks = getattr(bundle, "target_blocks", None)
    if not isinstance(target_blocks, list):
        return []
    return [block for block in target_blocks if isinstance(block, TaskTargetBlock)]


def _node_id_to_path(node_id: str | None) -> str | None:
    if not isinstance(node_id, str) or not node_id.startswith("file:"):
        return None
    return node_id.split("file:", 1)[1]


def _build_request_files(*, project_root: Path, relative_paths: list[str]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative_path in relative_paths:
        if relative_path in seen:
            continue
        seen.add(relative_path)
        file_path = _safe_generated_path(project_root, relative_path)
        exists = file_path.is_file()
        content = file_path.read_text(encoding="utf-8", errors="replace") if exists else ""
        files.append(
            {
                "path": relative_path,
                "exists": exists,
                "content": content,
            }
        )
    return files


def _post_model_request(
    *,
    api_url: str,
    api_token: str,
    api_payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    model_id = str(api_payload.get("model", "")).strip()
    messages = api_payload.get("messages")
    if not model_id:
        raise OptimizationExecutionError("Model request payload is missing model.")
    if not isinstance(messages, list):
        raise OptimizationExecutionError("Model request payload is missing messages list.")

    temperature_raw = api_payload.get("temperature", 0.7)
    max_tokens_raw = api_payload.get("max_tokens")
    try:
        temperature = float(temperature_raw)
    except (TypeError, ValueError) as error:
        raise OptimizationExecutionError(f"Invalid temperature in request payload: {temperature_raw}") from error

    max_tokens: int | None = None
    if max_tokens_raw is not None:
        try:
            max_tokens = int(max_tokens_raw)
        except (TypeError, ValueError) as error:
            raise OptimizationExecutionError(f"Invalid max_tokens in request payload: {max_tokens_raw}") from error

    try:
        result = request_chat_completion(
            model_id=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
    except LLMGatewayError as error:
        raise OptimizationExecutionError(str(error)) from error

    return {
        "choices": [
            {
                "message": {
                    "content": result.content,
                    "reasoning_content": result.reasoning_content,
                }
            }
        ],
        "model": result.model,
        "usage": result.usage,
        "latency_ms": result.latency_ms,
    }


def _extract_message_content(response_payload: dict[str, Any]) -> str:
    try:
        message_content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise OptimizationExecutionError("Model API response did not contain choices[0].message.content.") from error

    if isinstance(message_content, list):
        text_parts: list[str] = []
        for part in message_content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                text_parts.append(part)
        return "\n".join(part for part in text_parts if part).strip()
    if isinstance(message_content, str):
        return message_content.strip()
    raise OptimizationExecutionError("Model API returned an unsupported message.content format.")


def _parse_model_result(raw_model_content: str) -> dict[str, Any]:
    json_text = raw_model_content.strip()
    if json_text.startswith("```"):
        json_text = re.sub(r"^```(?:json)?\s*", "", json_text)
        json_text = re.sub(r"\s*```$", "", json_text)
    if not json_text.startswith("{"):
        start = json_text.find("{")
        end = json_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise OptimizationExecutionError("Model response did not contain a JSON object.")
        json_text = json_text[start : end + 1]
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise OptimizationExecutionError("Could not parse model JSON result.") from error
    if not isinstance(parsed, dict):
        raise OptimizationExecutionError("Model JSON result must be an object.")
    return parsed


def _optimization_status_from_payload(payload: dict[str, Any]) -> OptimizationStatus:
    status_raw = str(payload.get("status", OptimizationStatus.NEEDS_MANUAL_REVIEW.value))
    try:
        return OptimizationStatus(status_raw)
    except ValueError:
        return OptimizationStatus.NEEDS_MANUAL_REVIEW


def _changed_files_from_payload(payload: dict[str, Any]) -> list[OptimizedFile]:
    return [
        OptimizedFile(
            path=str(item.get("path", "")),
            content=str(item.get("content", "")),
            purpose=str(item.get("purpose", "")),
        )
        for item in payload.get("changed_files", [])
        if isinstance(item, dict) and item.get("path")
    ]


def _edits_from_payload(payload: dict[str, Any]) -> list[OptimizationEdit]:
    edits_raw = payload.get("edits", [])
    if not isinstance(edits_raw, list):
        return []

    edits: list[OptimizationEdit] = []
    for item in edits_raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        kind_raw = str(item.get("kind", OptimizationEditKind.REPLACE_BLOCK.value)).strip()
        try:
            kind = OptimizationEditKind(kind_raw)
        except ValueError as error:
            raise OptimizationExecutionError(f"Unsupported optimization edit kind: {kind_raw}") from error
        edits.append(
            OptimizationEdit(
                path=path,
                kind=kind,
                target_block_id=_optional_str(item.get("target_block_id")),
                start_line=_optional_int(item.get("start_line")),
                end_line=_optional_int(item.get("end_line")),
                old_text=_optional_str(item.get("old_text")),
                new_text=str(item.get("new_text", "")),
                purpose=str(item.get("purpose", "")),
            )
        )
    return edits


def _changed_files_from_edits(
    *,
    bundle: OptimizationPayload,
    project_root: Path,
    edits: list[OptimizationEdit],
) -> list[OptimizedFile]:
    editable_paths = set(_payload_editable_files(bundle))
    target_blocks_by_id = {block.id: block for block in _payload_target_blocks(bundle)}
    used_target_block_ids: set[str] = set()
    grouped_edits: dict[str, list[tuple[TaskTargetBlock, OptimizationEdit]]] = {}

    for edit in edits:
        if edit.kind is not OptimizationEditKind.REPLACE_BLOCK:
            raise OptimizationExecutionError(f"Unsupported optimization edit kind: {edit.kind.value}")
        if edit.path not in editable_paths:
            raise OptimizationExecutionError(
                f"Structured edit targets out-of-scope file {edit.path}; only editable_files may be changed."
            )
        target_block = _resolve_target_block_for_edit(
            edit=edit,
            target_blocks_by_id=target_blocks_by_id,
        )
        if target_block.id in used_target_block_ids:
            raise OptimizationExecutionError(
                f"Structured edit references target block {target_block.id} more than once."
            )
        used_target_block_ids.add(target_block.id)
        if target_block.path != edit.path:
            raise OptimizationExecutionError(
                f"Structured edit path {edit.path} does not match target block path {target_block.path}."
            )
        grouped_edits.setdefault(edit.path, []).append((target_block, edit))

    changed_files: list[OptimizedFile] = []
    for relative_path, block_edits in sorted(grouped_edits.items()):
        file_path = _safe_generated_path(project_root, relative_path)
        if not file_path.is_file():
            raise OptimizationExecutionError(
                f"Structured edit targets missing file {relative_path}; only existing editable files are supported."
            )
        original_text = file_path.read_text(encoding="utf-8", errors="replace")
        updated_text = _apply_replace_block_edits(
            original_text=original_text,
            relative_path=relative_path,
            block_edits=block_edits,
        )
        changed_files.append(
            OptimizedFile(
                path=relative_path,
                content=updated_text,
                purpose=_combined_edit_purpose(block_edits),
            )
        )
    return changed_files


def _resolve_target_block_for_edit(
    *,
    edit: OptimizationEdit,
    target_blocks_by_id: dict[str, TaskTargetBlock],
) -> TaskTargetBlock:
    if edit.target_block_id is not None:
        try:
            target_block = target_blocks_by_id[edit.target_block_id]
        except KeyError as error:
            raise OptimizationExecutionError(
                f"Structured edit references unknown target block {edit.target_block_id}."
            ) from error
        return target_block

    candidates = [
        block
        for block in target_blocks_by_id.values()
        if block.path == edit.path
        and block.start_line == edit.start_line
        and block.end_line == edit.end_line
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise OptimizationExecutionError(
        f"Structured edit for {edit.path} must include a valid target_block_id."
    )


def _apply_replace_block_edits(
    *,
    original_text: str,
    relative_path: str,
    block_edits: list[tuple[TaskTargetBlock, OptimizationEdit]],
) -> str:
    original_lines = original_text.splitlines()
    trailing_newline = original_text.endswith("\n")
    replacements: list[tuple[int, int, list[str]]] = []

    ordered_entries = sorted(block_edits, key=lambda item: item[0].start_line)
    previous_end = 0
    for target_block, edit in ordered_entries:
        start_index = max(target_block.start_line - 1, 0)
        end_index = max(target_block.end_line, start_index)
        if start_index < previous_end:
            raise OptimizationExecutionError(
                f"Structured edits for {relative_path} overlap around lines {target_block.start_line}-{target_block.end_line}."
            )
        previous_end = end_index

        current_text = "\n".join(original_lines[start_index:end_index])
        authoritative_text = _normalized_text(target_block.source_text)
        if current_text != authoritative_text:
            raise OptimizationExecutionError(
                f"Structured edit target {target_block.id} no longer matches the current file content."
            )
        if edit.start_line is not None and edit.start_line != target_block.start_line:
            raise OptimizationExecutionError(
                f"Structured edit start_line for {target_block.id} does not match the authoritative block location."
            )
        if edit.end_line is not None and edit.end_line != target_block.end_line:
            raise OptimizationExecutionError(
                f"Structured edit end_line for {target_block.id} does not match the authoritative block location."
            )
        normalized_authoritative = _normalized_block_text_for_comparison(target_block, authoritative_text)
        normalized_old_text = _normalized_block_text_for_comparison(target_block, edit.old_text or "")
        if edit.old_text is not None and normalized_old_text != normalized_authoritative:
            raise OptimizationExecutionError(
                f"Structured edit old_text for {target_block.id} does not match the authoritative block content."
            )
        replacements.append(
            (
                start_index,
                end_index,
                _aligned_replacement_lines(target_block=target_block, new_text=edit.new_text),
            )
        )

    updated_lines = list(original_lines)
    for start_index, end_index, replacement_lines in reversed(replacements):
        updated_lines[start_index:end_index] = replacement_lines

    updated_text = "\n".join(updated_lines)
    if trailing_newline and (updated_lines or original_text):
        updated_text += "\n"
    return updated_text


def _combined_edit_purpose(block_edits: list[tuple[TaskTargetBlock, OptimizationEdit]]) -> str:
    purposes = [edit.purpose.strip() for _, edit in block_edits if edit.purpose.strip()]
    if purposes:
        return "; ".join(dict.fromkeys(purposes))
    return "Apply structured block edits."


def _normalized_block_text_for_comparison(target_block: TaskTargetBlock, text: str) -> str:
    normalized = _normalized_text(text)
    if target_block.kind not in {CodeBlockKind.METHOD, CodeBlockKind.MODULE_SCOPE}:
        return normalized
    baseline = _leading_whitespace(_first_non_empty_line(target_block.source_text))
    if not baseline:
        return normalized
    return _strip_known_indent(normalized, baseline)


def _aligned_replacement_lines(*, target_block: TaskTargetBlock, new_text: str) -> list[str]:
    lines = new_text.splitlines()
    if target_block.kind not in {CodeBlockKind.METHOD, CodeBlockKind.MODULE_SCOPE}:
        return lines

    baseline = _leading_whitespace(_first_non_empty_line(target_block.source_text))
    if not baseline:
        return lines

    first_non_empty_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_non_empty_index is None:
        return lines
    if lines[first_non_empty_index].startswith(baseline):
        return lines

    expected_relative_indent = _expected_relative_indent(target_block.source_text)
    new_relative_indent = _expected_relative_indent(new_text)
    align_first_line_only = (
        new_relative_indent is not None
        and expected_relative_indent is not None
        and new_relative_indent > expected_relative_indent
    )

    adjusted_lines = list(lines)
    if align_first_line_only:
        if adjusted_lines[first_non_empty_index].strip():
            adjusted_lines[first_non_empty_index] = baseline + adjusted_lines[first_non_empty_index]
        for index, line in enumerate(adjusted_lines):
            if index == first_non_empty_index or not line.strip():
                continue
            if len(_leading_whitespace(line)) < len(baseline):
                adjusted_lines[index] = baseline + line
        return adjusted_lines

    return [
        (baseline + line) if line.strip() else line
        for line in adjusted_lines
    ]


def _candidate_safety_violations(
    *,
    bundle: OptimizationPayload,
    project_root: Path,
    changed_files: list[OptimizedFile],
) -> list[str]:
    if not changed_files:
        return []

    editable_paths = set(_payload_editable_files(bundle))
    violations: list[str] = []
    for changed_file in changed_files:
        if changed_file.path not in editable_paths:
            violations.append(
                f"Model tried to edit out-of-scope file {changed_file.path}; only editable_files may be changed."
            )
            continue

        target_path = _safe_generated_path(project_root, changed_file.path)
        if not target_path.is_file():
            continue
        original_text = target_path.read_text(encoding="utf-8", errors="replace")
        missing_definitions = _missing_top_level_definitions(original_text, changed_file.content)
        if missing_definitions:
            violations.append(
                f"Model removed top-level definitions from {changed_file.path}: {', '.join(sorted(missing_definitions))}."
            )
    return violations


def _missing_top_level_definitions(original_text: str, candidate_text: str) -> set[str]:
    original_defs = _top_level_definition_names(original_text)
    candidate_defs = _top_level_definition_names(candidate_text)
    if original_defs is None or candidate_defs is None:
        return set()
    return original_defs - candidate_defs


def _top_level_definition_names(source_text: str) -> set[str] | None:
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return None
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def _capture_original_files(
    *,
    project_root: Path,
    changed_files: list[OptimizedFile],
    output_dir: Path,
) -> list[OriginalFileState]:
    original_files: list[OriginalFileState] = []
    original_root = output_dir / "original_files"
    for changed_file in changed_files:
        target_path = _safe_generated_path(project_root, changed_file.path)
        existed_before = target_path.is_file()
        content = target_path.read_text(encoding="utf-8", errors="replace") if existed_before else ""
        original_files.append(
            OriginalFileState(
                path=changed_file.path,
                existed_before=existed_before,
                content=content,
            )
        )
        snapshot_path = _safe_generated_path(original_root, changed_file.path)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(content, encoding="utf-8")
    _write_json(output_dir / "original_files.json", _json_ready(original_files))
    return original_files


def _build_unified_diff(*, project_root: Path, changed_files: list[OptimizedFile]) -> str:
    patches: list[str] = []
    for changed_file in changed_files:
        target_path = _safe_generated_path(project_root, changed_file.path)
        original_text = target_path.read_text(encoding="utf-8", errors="replace") if target_path.is_file() else ""
        diff_lines = difflib.unified_diff(
            original_text.splitlines(),
            changed_file.content.splitlines(),
            fromfile=str(changed_file.path),
            tofile=str(changed_file.path),
            lineterm="",
        )
        patch = "\n".join(diff_lines).strip()
        if patch:
            patches.append(patch)
    return "\n\n".join(patches) + ("\n" if patches else "")


def _run_command(command: list[str], *, cwd: Path) -> ValidationCommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        return ValidationCommandResult(
            command=" ".join(command),
            returncode=124,
            stdout=error.stdout or "",
            stderr=(error.stderr or "") + "\nCommand timed out.",
            ok=False,
        )
    return ValidationCommandResult(
        command=" ".join(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        ok=completed.returncode == 0,
    )


def _run_validation_commands(
    *,
    workspace_dir: Path,
    validation_notes: list[str],
    suggested_tests: list[str],
) -> OptimizationValidationReport:
    compile_result = _run_command(["python3", "-m", "compileall", "."], cwd=workspace_dir)
    test_result: ValidationCommandResult | None = None
    if (workspace_dir / "tests").is_dir():
        test_result = _run_command(["python3", "-m", "unittest", "discover", "-s", "tests"], cwd=workspace_dir)

    if not compile_result.ok:
        status = ValidationStatus.BLOCKED
    elif test_result is not None and not test_result.ok:
        status = ValidationStatus.NEEDS_REVIEW
    else:
        status = ValidationStatus.PASSED

    notes = list(validation_notes)
    if suggested_tests:
        notes.append("Suggested tests: " + "; ".join(suggested_tests))

    return OptimizationValidationReport(
        status=status,
        workspace_dir=str(workspace_dir),
        compile_command=compile_result,
        test_command=test_result,
        notes=notes,
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalized_text(value: str) -> str:
    return "\n".join(value.splitlines())


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line
    return ""


def _leading_whitespace(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _strip_known_indent(text: str, indent: str) -> str:
    stripped_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith(indent):
            stripped_lines.append(line[len(indent) :])
        else:
            stripped_lines.append(line)
    return "\n".join(stripped_lines)


def _expected_relative_indent(text: str) -> int | None:
    non_empty_lines = [line for line in text.splitlines() if line.strip()]
    if len(non_empty_lines) < 2:
        return None
    first_indent = len(_leading_whitespace(non_empty_lines[0]))
    second_indent = len(_leading_whitespace(non_empty_lines[1]))
    return max(second_indent - first_indent, 0)


def _assert_workspace_matches_original(*, project_root: Path, original_files: list[OriginalFileState]) -> None:
    for original_file in original_files:
        target_path = _safe_generated_path(project_root, original_file.path)
        if not original_file.existed_before:
            if target_path.exists():
                raise OptimizationExecutionError(
                    f"Cannot apply optimization because {original_file.path} now exists in the workspace."
                )
            continue
        if not target_path.is_file():
            raise OptimizationExecutionError(
                f"Cannot apply optimization because {original_file.path} no longer exists in the workspace."
            )
        current_content = target_path.read_text(encoding="utf-8", errors="replace")
        if current_content != original_file.content:
            raise OptimizationExecutionError(
                f"Cannot apply optimization because {original_file.path} changed after the diff preview was generated."
            )


def _assert_workspace_matches_candidate(*, project_root: Path, changed_files: list[OptimizedFile]) -> None:
    for changed_file in changed_files:
        target_path = _safe_generated_path(project_root, changed_file.path)
        if not target_path.is_file():
            raise OptimizationExecutionError(
                f"Cannot roll back because {changed_file.path} is missing from the workspace."
            )
        current_content = target_path.read_text(encoding="utf-8", errors="replace")
        if current_content != changed_file.content:
            raise OptimizationExecutionError(
                f"Cannot roll back because {changed_file.path} changed after the optimization patch was applied."
            )


def _safe_generated_path(root_dir: Path, relative_path: str) -> Path:
    normalized = PurePosixPath(relative_path)
    if normalized.is_absolute():
        raise OptimizationExecutionError(f"Generated file path must be relative: {relative_path}")
    if ".." in normalized.parts:
        raise OptimizationExecutionError(f"Generated file path cannot escape the workspace: {relative_path}")
    return root_dir.joinpath(*normalized.parts)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(_json_ready(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _json_ready(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
