from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from GhostLib import GhostClient


def load_adapter_class(class_name: str = "Dict2ModelAdapter"):
    module = importlib.import_module("pkg.Dict2MODEL")
    return getattr(module, class_name)


def load_by_name(module_name: str):
    return importlib.import_module(module_name)
