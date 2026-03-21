from __future__ import annotations


class Component:
    def __init__(self, name: str, retries: int) -> None:
        self.name = name
        self.retries = retries

    @classmethod
    def from_name(cls, name: str, retries: int = 1) -> "Component":
        return cls(name=name.strip(), retries=retries)

    @staticmethod
    def build_slug(name: str) -> str:
        return name.strip().lower().replace(" ", "-")

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.retries})"
