from __future__ import annotations

import json as json_lib

from pkg import DEFAULT_RETRIES
from pkg.Component import Component
from pkg.handlers import bulk_handle
from pkg.models import RecordStatus, make_record
from pkg.service import DataService, summarize_records

batch_service = DataService("batch-runner", DEFAULT_RETRIES)
component = Component.from_name("batch-component", retries=1)


def build_payloads() -> list[dict[str, object]]:
    seed_record = make_record("B-0", " seed record ", RecordStatus.NEW, [" Seed "])
    return [
        {"id": seed_record.identifier, "title": seed_record.title, "tags": seed_record.tags},
        {"id": "B-1", "title": " second seed ", "status": RecordStatus.ARCHIVED.value},
    ]


def main() -> str:
    records = batch_service.prepare_records(build_payloads())
    normalized = bulk_handle(records)
    result = {
        "component": component.display_name,
        "summary": summarize_records(normalized),
    }
    return json_lib.dumps(result, sort_keys=True)


if __name__ == "__main__":
    print(main())
