from __future__ import annotations

import asyncio

try:
    import requests
except ImportError:
    requests = None

import pkg.Component as component_module
from pkg.Dict2MODEL import Dict2ModelAdapter
from pkg.constants import DEFAULT_RETRIES

from .decorators import trace_call
from .dynamic_loader import load_adapter_class
from .handlers import NormalizingHandler
from .models import Record, RecordStatus

DEFAULT_COMPONENT = component_module.Component.from_name("core-service", DEFAULT_RETRIES)


class DataService:
    def __init__(self, name: str, retries: int = DEFAULT_RETRIES) -> None:
        self.component = component_module.Component.from_name(name, retries)

    @classmethod
    def build_default(cls, name: str = "service") -> "DataService":
        return cls(name=name, retries=DEFAULT_RETRIES)

    @trace_call
    def prepare_records(self, payloads: list[dict[str, object]]) -> list[Record]:
        adapter = Dict2ModelAdapter(default_status=RecordStatus.NEW)
        prepared = adapter.coerce_many(payloads)
        handler = NormalizingHandler(self.component.name)
        return [handler.handle(adapter.to_record(payload)) for payload in prepared]

    async def warm_cache(self, module_name: str = "pkg.Dict2MODEL") -> str:
        await asyncio.sleep(0)
        adapter_class = load_adapter_class()
        return f"{module_name}:{adapter_class.__name__}"

    @property
    def component_slug(self) -> str:
        return self.component.build_slug(self.component.name)


@trace_call
def summarize_records(records: list[Record]) -> dict[str, int]:
    summary: dict[str, int] = {}

    def bump(key: str) -> None:
        summary[key] = summary.get(key, 0) + 1

    for record in records:
        bump(record.status.value)

    if requests is not None and not summary:
        bump("network-ready")

    return summary
