from __future__ import annotations

from pkg.constants import ARCHIVE_SUFFIX

from .decorators import trace_call
from .models import AuditRecord, Record, make_record


class BaseHandler:
    def handle(self, record: Record) -> Record:
        return record


class NormalizingHandler(BaseHandler):
    def __init__(self, source: str) -> None:
        self.source = source

    @trace_call
    def handle(self, record: Record) -> Record:
        cleaned = self.normalize(record)
        return make_record(cleaned.identifier, cleaned.title, cleaned.status, cleaned.tags)

    def normalize(self, record: Record) -> Record:
        title = " ".join(part for part in record.title.split())
        return Record(
            identifier=record.identifier,
            title=title.title(),
            status=record.status,
            tags=record.tags,
        )


def build_archive_name(record: Record, audit: AuditRecord | None = None) -> str:
    return f"{record.identifier}{ARCHIVE_SUFFIX}"


def bulk_handle(records: list[Record]) -> list[Record]:
    handler = NormalizingHandler("bulk")
    return [handler.handle(record) for record in records]


HANDLER = NormalizingHandler("module-default")
