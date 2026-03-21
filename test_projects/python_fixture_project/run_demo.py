from __future__ import annotations

from pkg import DEFAULT_RETRIES
from pkg.handlers import HANDLER, build_archive_name
from pkg.models import RecordStatus, make_record
from pkg.service import DataService, summarize_records

service = DataService("demo-runner", DEFAULT_RETRIES)
sample_payloads = [
    {"id": "A-1", "title": " first item ", "tags": [" Hot ", " Demo "]},
    {"id": "A-2", "title": "second item", "status": RecordStatus.READY.value, "tags": []},
]
records = service.prepare_records(sample_payloads)
summary = summarize_records(records)
archive_name = build_archive_name(records[0])
preview = HANDLER.handle(make_record("A-3", "manual item"))


def main() -> dict[str, object]:
    return {
        "archive_name": archive_name,
        "preview_title": preview.title,
        "summary": summary,
    }


if __name__ == "__main__":
    print(main())
