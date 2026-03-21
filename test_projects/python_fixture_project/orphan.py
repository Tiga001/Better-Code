class GhostCounter:
    def __init__(self) -> None:
        self.total = 0

    def bump(self, amount: int = 1) -> int:
        self.total += amount
        return self.total


def unused_probe(values: list[int]) -> int:
    return sum(values)
