from __future__ import annotations

from . import cycle_a


def ping_b(depth: int = 0) -> str:
    if depth > 0:
        return "b"
    return f"b->{cycle_a.ping_a(depth + 1)}"


class CycleB:
    def partner(self) -> str:
        return cycle_a.ping_a(1)
