# Python Fixture Project

This fixture is a small but broad Python project for manual BetterCode testing.

It intentionally mixes:

- top-level scripts
- package files with absolute and relative imports
- leaf files, ordinary internal files, isolated files, and a cycle
- decorators, dataclasses, enums, async functions, nested functions, and properties
- external imports, standard library imports, unresolved imports, and a syntax error

Some files are intentionally not runnable in every environment:

- `broken_syntax.py` contains a syntax error
- `pkg/dynamic_loader.py` contains an unresolved import under `TYPE_CHECKING`
- `pkg/service.py` and `pkg/Dict2MODEL.py` reference optional third-party packages

The project is designed to be parsed statically, not to act as a full application.
