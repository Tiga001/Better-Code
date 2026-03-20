# BetterCode

BetterCode is a pure Python desktop application for exploring Python project structure.

The current MVP focuses on:

- importing a local project directory
- parsing file-level Python dependencies
- displaying a directed dependency graph in a PySide6 desktop UI

## Stack

- Python 3.11+
- PySide6
- Python `ast` for static analysis

## Run

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

## Tests

```bash
python3 -m unittest discover -s tests
```

## Notes

- The parser ignores common virtual environment, cache, and build directories.
- Dynamic imports are not resolved in this version.
- The graph is file-level only in this version.

