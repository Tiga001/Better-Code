# BetterCode

BetterCode is a pure Python desktop application for exploring Python project structure.

The current MVP focuses on:

- importing a local project directory
- parsing file-level Python dependencies
- displaying a directed dependency graph in a PySide6 desktop UI
- generating task bundles for optimization and translation workflows

## Stack

- Python 3.11+
- PySide6
- Python `ast` for static analysis

## Run

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

## Translation MVP

The current translation executor targets one Python top-level function at a time and writes all generated artifacts to `generated/translations/`.

Set these environment variables before running a translation job:

```bash
export BETTERCODE_MODEL_API_TOKEN="your-token"
export BETTERCODE_MODEL_API_URL="https://zju.smartml.cn/userapi/v1/model/v1/chat/completions"   # optional
export BETTERCODE_MODEL_NAME="deepseek/deepseek-v3.1-terminus-thinking"                          # optional
```

If you do not want to set environment variables, you can also open the code-block dialog, switch to `任务候选 / Task Candidates`, and fill the API URL, token, and model name through the `API 配置 / Model Config` button.

Translation jobs currently:

- call a chat-completions compatible endpoint
- ask the model for C++20 + CMake + pybind11 output
- save request/response/result files under `generated/translations/`
- do not modify the imported project source tree

## Tests

```bash
python3 -m unittest discover -s tests
```

## Notes

- The parser ignores common virtual environment, cache, and build directories.
- Dynamic imports are not resolved in this version.
- The graph is file-level only in this version.
