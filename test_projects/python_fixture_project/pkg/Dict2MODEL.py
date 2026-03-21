from __future__ import annotations

try:
    import numpy as np
except ImportError:
    np = None

from pkg.models import Record, RecordStatus, make_record


class Dict2ModelAdapter:
    def __init__(self, default_status: RecordStatus = RecordStatus.NEW) -> None:
        self.default_status = default_status

    def to_record(self, payload: dict[str, object]) -> Record:
        title = str(payload.get("title", "untitled"))
        raw_tags = payload.get("tags", [])
        tags = [str(item) for item in raw_tags] if isinstance(raw_tags, list) else []
        status_value = str(payload.get("status", self.default_status.value))
        try:
            status = RecordStatus(status_value)
        except ValueError:
            status = self.default_status
        return make_record(
            identifier=str(payload.get("id", "unknown")),
            title=title,
            status=status,
            tags=tags,
        )

    @staticmethod
    def coerce_many(payloads: list[dict[str, object]]) -> list[dict[str, object]]:
        if np is None:
            return [dict(item) for item in payloads]
        return [dict(item) for item in np.asarray(payloads, dtype=object).tolist()]
