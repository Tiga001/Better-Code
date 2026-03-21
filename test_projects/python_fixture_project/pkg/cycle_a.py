from __future__ import annotations

from . import cycle_b


def ping_a(depth: int = 0) -> str:
    if depth > 0:
        return "a"
    return f"a->{cycle_b.ping_b(depth + 1)}"


class CycleA:
    def partner(self) -> str:
        return cycle_b.ping_b(1)
