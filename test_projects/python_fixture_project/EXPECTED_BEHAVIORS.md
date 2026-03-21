# Expected Behaviors

## File roles

- Top-level scripts: `run_demo.py`, `batch_runner.py`
- Leaf files: `pkg/constants.py`, `pkg/decorators.py`, `pkg/models.py`, `pkg/dynamic_loader.py`, `pkg/Component.py`
- Ordinary internal files: `pkg/__init__.py`, `pkg/service.py`, `pkg/handlers.py`, `pkg/Dict2MODEL.py`, `pkg/cycle_a.py`, `pkg/cycle_b.py`
- Isolated files: `orphan.py`, `broken_syntax.py`

## Cycle and subsystem expectations

- The intentional cycle is `pkg/cycle_a.py <-> pkg/cycle_b.py`
- The main subsystem should contain the two scripts plus `pkg/__init__.py`, `pkg/service.py`, `pkg/handlers.py`, `pkg/Dict2MODEL.py`, `pkg/models.py`, `pkg/constants.py`, `pkg/decorators.py`, `pkg/dynamic_loader.py`, and `pkg/Component.py`
- `pkg/cycle_a.py` and `pkg/cycle_b.py` should form a separate small subsystem
- `orphan.py` should remain fully disconnected
- `broken_syntax.py` should remain disconnected and report a syntax error

## Import classification expectations

- External imports:
  - `pkg/service.py` -> `requests`
  - `pkg/Dict2MODEL.py` -> `numpy`
- Standard library imports:
  - `batch_runner.py` -> `json`
  - `pkg/service.py` -> `asyncio`
  - `pkg/decorators.py` -> `functools`, `typing`
  - `pkg/dynamic_loader.py` -> `importlib`, `typing`
  - `pkg/models.py` -> `dataclasses`, `enum`
- Unresolved imports:
  - `pkg/dynamic_loader.py` -> `GhostLib.GhostClient`
- Internal mixed-case files that should still be recognized as internal:
  - `pkg/Component.py`
  - `pkg/Dict2MODEL.py`

## File detail parsing expectations

- `pkg/models.py` should expose:
  - classes `Record`, `AuditRecord`
  - enum `RecordStatus`
  - top-level function `make_record`
  - nested function `normalize` inside `make_record`
- `pkg/service.py` should expose:
  - class `DataService`
  - methods `__init__`, `build_default`, `prepare_records`, `warm_cache`, `component_slug`
  - top-level function `summarize_records`
  - decorator usage on `prepare_records` and `summarize_records`
  - async function `warm_cache`
- `pkg/handlers.py` should expose:
  - classes `BaseHandler`, `NormalizingHandler`
  - methods `handle`, `normalize`
  - top-level functions `build_archive_name`, `bulk_handle`
  - module-level instance `HANDLER`
- `pkg/Component.py` should expose:
  - class `Component`
  - `@classmethod from_name`
  - `@staticmethod build_slug`
  - `@property display_name`

## Call and usage expectations

- Cross-file function calls:
  - `pkg/handlers.py` calls `pkg.models.make_record`
  - `run_demo.py` and `batch_runner.py` call `pkg.service.summarize_records`
- Cross-file class instantiation:
  - `run_demo.py` instantiates `pkg.service.DataService`
  - `batch_runner.py` instantiates `pkg.service.DataService`
  - `pkg/service.py` instantiates `pkg.Dict2MODEL.Dict2ModelAdapter` and `pkg.handlers.NormalizingHandler`
- Cross-file method calls:
  - `run_demo.py` calls `DataService.prepare_records`
  - `pkg/service.py` calls `Dict2ModelAdapter.to_record`
  - `pkg/service.py` calls `NormalizingHandler.handle`
  - `batch_runner.py` uses `Component.display_name`

## Find Usages examples

- `pkg.service.summarize_records`
  - imported by `pkg/__init__.py`
  - imported and called by `run_demo.py`
  - imported and called by `batch_runner.py`
- `pkg.models.make_record`
  - imported and called by `pkg/handlers.py`
  - imported and called by `run_demo.py`
  - imported and called by `batch_runner.py`
- `pkg.handlers.NormalizingHandler`
  - instantiated in `pkg/handlers.py`
  - imported and instantiated in `pkg/service.py`

## Boundary cases

- `broken_syntax.py` should surface a syntax error instead of crashing parsing
- `pkg/dynamic_loader.py` uses `importlib.import_module("pkg.Dict2MODEL")`; this is a dynamic import boundary and should not require a static edge from that string alone
- `pkg.handlers.build_archive_name` references `AuditRecord` only in a type annotation; there is no real call or instantiation of `AuditRecord`
