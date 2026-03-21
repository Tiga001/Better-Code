from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bettercode.models import TaskBundle, TaskMode
from bettercode.task_planner import task_bundle_to_dict

DEFAULT_MODEL_API_URL = "https://zju.smartml.cn/userapi/v1/model/v1/chat/completions"
DEFAULT_MODEL_NAME = "deepseek/deepseek-v3.1-terminus-thinking"
DEFAULT_TIMEOUT_SECONDS = 180.0


class TranslationStatus(str, Enum):
    TRANSLATED = "translated"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    BLOCKED = "blocked"


@dataclass(slots=True)
class ModelConfig:
    api_url: str
    api_token: str
    model_name: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "ModelConfig":
        api_token = (os.environ.get("BETTERCODE_MODEL_API_TOKEN") or os.environ.get("API_TOKEN") or "").strip()
        if not api_token:
            raise TranslationConfigError(
                "Missing BETTERCODE_MODEL_API_TOKEN. Set the token in your environment before running translation."
            )

        api_url = os.environ.get("BETTERCODE_MODEL_API_URL", DEFAULT_MODEL_API_URL).strip()
        model_name = os.environ.get("BETTERCODE_MODEL_NAME", DEFAULT_MODEL_NAME).strip()
        timeout_raw = os.environ.get("BETTERCODE_MODEL_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)).strip()
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as error:
            raise TranslationConfigError(
                "BETTERCODE_MODEL_TIMEOUT_SECONDS must be a number."
            ) from error

        return cls(
            api_url=api_url,
            api_token=api_token,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
        )


@dataclass(slots=True)
class GeneratedFile:
    path: str
    content: str
    purpose: str


@dataclass(slots=True)
class ComparisonCase:
    label: str
    python_expression: str
    notes: str = ""


@dataclass(slots=True)
class TranslationVerificationPlan:
    python_test_commands: list[str]
    comparison_cases: list[ComparisonCase]
    notes: list[str]


@dataclass(slots=True)
class TranslationRequest:
    system_prompt: str
    user_payload: dict[str, Any]
    api_payload: dict[str, Any]


@dataclass(slots=True)
class TranslationResult:
    status: TranslationStatus
    summary: str
    assumptions: list[str]
    risks: list[str]
    dependency_mapping_notes: list[str]
    verification_notes: list[str]
    comparison_cases: list[ComparisonCase]
    generated_files: list[GeneratedFile]
    raw_model_content: str
    output_dir: str


class TranslationExecutionError(RuntimeError):
    pass


class TranslationConfigError(TranslationExecutionError):
    pass


def execute_translation(
    bundle: TaskBundle,
    *,
    project_root: Path,
    output_root: Path | None = None,
    config: ModelConfig | None = None,
) -> TranslationResult:
    if bundle.task.mode is not TaskMode.TRANSLATE:
        raise TranslationExecutionError("Translation executor only accepts translate task bundles.")

    model_config = config or ModelConfig.from_env()
    request_payload = build_translation_request(bundle, config=model_config)
    destination = _build_output_directory(
        base_dir=output_root or (project_root / "generated" / "translations"),
        task_id=bundle.task.id,
    )
    destination.mkdir(parents=True, exist_ok=True)

    _write_json(destination / "task_bundle.json", task_bundle_to_dict(bundle))
    _write_json(
        destination / "translation_request.json",
        {
            "system_prompt": request_payload.system_prompt,
            "user_payload": request_payload.user_payload,
            "api_payload": request_payload.api_payload,
        },
    )

    response_payload = _post_translation_request(
        api_url=model_config.api_url,
        api_token=model_config.api_token,
        api_payload=request_payload.api_payload,
        timeout_seconds=model_config.timeout_seconds,
    )
    _write_json(destination / "translation_response.json", response_payload)

    raw_model_content = _extract_message_content(response_payload)
    parsed_result = _parse_model_result(raw_model_content)
    translation_result = _translation_result_from_payload(
        parsed_result,
        raw_model_content=raw_model_content,
        output_dir=destination,
    )

    for generated_file in translation_result.generated_files:
        output_path = _safe_generated_path(destination, generated_file.path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generated_file.content, encoding="utf-8")

    verification_plan = build_verification_plan(project_root=project_root, result=translation_result)
    _write_json(destination / "verification_plan.json", _json_ready(verification_plan))
    _write_json(destination / "translation_result.json", _json_ready(translation_result))
    return translation_result


def build_translation_request(bundle: TaskBundle, *, config: ModelConfig) -> TranslationRequest:
    if bundle.task.mode is not TaskMode.TRANSLATE:
        raise TranslationExecutionError("Only translate task bundles can be sent to the translation model.")

    system_prompt = (
        "You are a senior Python-to-C++ migration engineer. "
        "Translate exactly one Python top-level function into a C++20 implementation with a pybind11 bridge. "
        "Preserve observable behavior, keep surrounding Python workflow stable, and return only valid JSON. "
        "Do not wrap the JSON in markdown fences. "
        "Use this JSON schema: "
        '{"status":"translated|needs_manual_review|blocked",'
        '"summary":"...",'
        '"assumptions":["..."],'
        '"risks":["..."],'
        '"dependency_mapping_notes":["..."],'
        '"verification_notes":["..."],'
        '"comparison_cases":[{"label":"...","python_expression":"...","notes":"..."}],'
        '"generated_files":[{"path":"relative/path","purpose":"short description","content":"file contents"}]}'
    )
    user_payload = {
        "task_bundle": task_bundle_to_dict(bundle),
        "translation_constraints": {
            "target_language": "cpp",
            "cpp_standard": "c++20",
            "build_system": "cmake",
            "bridge": "pybind11",
            "output_scope": "function-level",
            "write_back_policy": "generated_only",
        },
        "required_outputs": [
            "CMakeLists.txt",
            "src/<function>.cpp",
            "include/<function>.hpp",
            "src/bindings.cpp",
        ],
        "rules": [
            "Preserve the Python function signature and behavior as closely as possible.",
            "If a dependency cannot be mapped safely, set status to needs_manual_review or blocked and explain why.",
            "Keep all file paths relative and suitable for a standalone generated translation workspace.",
            "Add brief comments only where behavior would otherwise be unclear.",
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
    return TranslationRequest(
        system_prompt=system_prompt,
        user_payload=user_payload,
        api_payload=api_payload,
    )


def build_verification_plan(
    *,
    project_root: Path,
    result: TranslationResult,
) -> TranslationVerificationPlan:
    python_test_commands: list[str] = []
    if (project_root / "tests").is_dir():
        python_test_commands.append("python3 -m unittest discover -s tests")
    python_test_commands.append("python3 -m compileall .")

    notes = [
        "Compile the generated C++ workspace before running cross-language comparisons.",
        "After building the pybind11 module, compare each generated comparison case against the Python original.",
    ]
    notes.extend(result.verification_notes)

    if not result.comparison_cases:
        notes.append("The model did not provide concrete comparison cases; create manual cases before validating equivalence.")

    return TranslationVerificationPlan(
        python_test_commands=python_test_commands,
        comparison_cases=result.comparison_cases,
        notes=notes,
    )


def _build_output_directory(*, base_dir: Path, task_id: str) -> Path:
    safe_task_id = re.sub(r"[^A-Za-z0-9._-]+", "_", task_id).strip("._") or "translation_task"
    candidate = base_dir / safe_task_id
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        fallback = base_dir / f"{safe_task_id}_{suffix}"
        if not fallback.exists():
            return fallback
        suffix += 1


def _post_translation_request(
    *,
    api_url: str,
    api_token: str,
    api_payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    request = Request(
        api_url,
        data=json.dumps(api_payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise TranslationExecutionError(f"Model API returned HTTP {error.code}: {body}") from error
    except URLError as error:
        raise TranslationExecutionError(f"Could not reach model API: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise TranslationExecutionError("Model API returned non-JSON HTTP payload.") from error


def _extract_message_content(response_payload: dict[str, Any]) -> str:
    try:
        message_content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise TranslationExecutionError("Model API response did not contain choices[0].message.content.") from error

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
    raise TranslationExecutionError("Model API returned an unsupported message.content format.")


def _parse_model_result(raw_model_content: str) -> dict[str, Any]:
    json_text = raw_model_content.strip()
    if json_text.startswith("```"):
        json_text = re.sub(r"^```(?:json)?\s*", "", json_text)
        json_text = re.sub(r"\s*```$", "", json_text)
    if not json_text.startswith("{"):
        start = json_text.find("{")
        end = json_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise TranslationExecutionError("Model response did not contain a JSON object.")
        json_text = json_text[start : end + 1]
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise TranslationExecutionError("Could not parse model JSON result.") from error
    if not isinstance(parsed, dict):
        raise TranslationExecutionError("Model JSON result must be an object.")
    return parsed


def _translation_result_from_payload(
    payload: dict[str, Any],
    *,
    raw_model_content: str,
    output_dir: Path,
) -> TranslationResult:
    status_raw = str(payload.get("status", TranslationStatus.NEEDS_MANUAL_REVIEW.value))
    try:
        status = TranslationStatus(status_raw)
    except ValueError:
        status = TranslationStatus.NEEDS_MANUAL_REVIEW

    generated_files = [
        GeneratedFile(
            path=str(item.get("path", "")),
            content=str(item.get("content", "")),
            purpose=str(item.get("purpose", "")),
        )
        for item in payload.get("generated_files", [])
        if isinstance(item, dict) and item.get("path")
    ]
    comparison_cases = [
        ComparisonCase(
            label=str(item.get("label", "")),
            python_expression=str(item.get("python_expression", "")),
            notes=str(item.get("notes", "")),
        )
        for item in payload.get("comparison_cases", [])
        if isinstance(item, dict) and item.get("label") and item.get("python_expression")
    ]
    return TranslationResult(
        status=status,
        summary=str(payload.get("summary", "")).strip() or "No summary returned.",
        assumptions=_string_list(payload.get("assumptions")),
        risks=_string_list(payload.get("risks")),
        dependency_mapping_notes=_string_list(payload.get("dependency_mapping_notes")),
        verification_notes=_string_list(payload.get("verification_notes")),
        comparison_cases=comparison_cases,
        generated_files=generated_files,
        raw_model_content=raw_model_content,
        output_dir=str(output_dir),
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _safe_generated_path(output_dir: Path, relative_path: str) -> Path:
    normalized = PurePosixPath(relative_path)
    if normalized.is_absolute():
        raise TranslationExecutionError(f"Generated file path must be relative: {relative_path}")
    if ".." in normalized.parts:
        raise TranslationExecutionError(f"Generated file path cannot escape the output directory: {relative_path}")
    filesystem_path = output_dir.joinpath(*normalized.parts)
    return filesystem_path


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
