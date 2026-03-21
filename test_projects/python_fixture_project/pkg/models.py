from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RecordStatus(str, Enum):
    NEW = "new"
    READY = "ready"
    ARCHIVED = "archived"


@dataclass(slots=True)
class Record:
    identifier: str
    title: str
    status: RecordStatus = RecordStatus.NEW
    tags: list[str] = field(default_factory=list)

    def mark_ready(self) -> "Record":
        self.status = RecordStatus.READY
        return self


@dataclass(slots=True)
class AuditRecord:
    record_id: str
    actor: str
    note: str


def make_record(
    identifier: str,
    title: str,
    status: RecordStatus = RecordStatus.NEW,
    tags: list[str] | None = None,
) -> Record:
    def normalize(items: list[str] | None) -> list[str]:
        return [item.strip().lower() for item in items or [] if item.strip()]

    return Record(
        identifier=identifier,
        title=title.strip(),
        status=status,
        tags=normalize(tags),
    )
