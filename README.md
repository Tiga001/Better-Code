# BetterCode

[中文](#中文) | [English](#english)

BetterCode is a Python desktop workbench for understanding a codebase, decomposing it into tasks, and running AI-assisted optimization workflows.

---

## 中文

### 这是什么

BetterCode 是一个面向 Python 项目的桌面工具。  
它的目标不是单纯“画依赖图”，而是把项目解析、任务拆分、执行顺序、优化预览和回滚放到一个工作台里。

### 现在能做什么

- 导入本地 Python 项目
- 解析文件级依赖关系
- 展示 4 个视图：
  - 依赖图
  - 子系统
  - 任务图
  - 批次视图
- 提取代码块：
  - 函数
  - 类 / 方法
  - 顶层脚本块
- 查看调用关系、引用位置和任务形成原因
- 对单个任务执行优化闭环：
  - 预览 diff
  - 预验证
  - 应用
  - 回滚
- 按 phase 执行优化批次并监控状态
- 将四张画布导出为 `SVG / PNG / JPG`

### 适合谁

- 需要先“看懂项目结构”再做改造的人
- 想把代码改造任务拆小、排序、审阅的人
- 想把 AI 优化流程做成可视化工作台的人

### 快速运行

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

### 快速测试

```bash
python3 -m unittest discover -s tests
```

### LLM 适配方式（当前）

- 统一配置：`bettercode/config/config.yaml`（按 `model_id` 管理）
- 统一客户端工厂：`bettercode/llm/factory.py`
- 统一调用网关：`bettercode/llm/gateway.py`
- 执行器接入：
  - `bettercode/translation_executor.py`
  - `bettercode/optimize_executor.py`

说明：`translation_executor` 和 `optimize_executor` 已不再直接依赖底层 HTTP 细节，而是通过 `llm/gateway` 走统一链路。

### LLM 调用流程（后端）

1. 业务执行器构建 prompt 和 `messages`
2. 调用 `llm.gateway.request_chat_completion(...)`
3. `gateway` 内部使用 `create_llm_client(model_id)` 选择具体 provider 客户端
4. 客户端向云端模型发起请求并返回统一响应
5. 执行器继续做既有的 JSON 解析、校验、产物落盘与验证

### 模型配置与连通性检查

```bash
python3 -m bettercode.cli.main config --model <model_id> --provider <provider> --api-key <api_key> [--base-url <url>]
python3 tests/test_llm_client.py --model <model_id> --prompt "连接测试"
```

### 当前状态

- 主线已经是：**项目解析 + 任务图 + 优化闭环**
- 翻译功能还在实验阶段（已接入统一 LLM 网关链路）
- 验证体系目前是基础安全网，不算完备
- 仍以静态分析为主，对动态特性支持有限
- UI 配置链路仍在逐步收敛到统一 LLM 配置

### 项目结构

```text
bettercode/
  app.py
  bettercode/
    cli/
    llm/
    parser.py
    task_graph.py
    task_planner.py
    optimize_executor.py
    translation_executor.py
    ui/
  tests/
```

---

## English

### What It Is

BetterCode is a desktop tool for Python codebases.  
It is not just a dependency viewer. The goal is to combine project parsing, task decomposition, execution ordering, optimization preview, and rollback in one workbench.

### What It Can Do Today

- Import a local Python project
- Parse file-level dependencies
- Show 4 graph views:
  - Dependency Graph
  - Subsystems
  - Task Graph
  - Batch / Phase View
- Extract code blocks:
  - functions
  - classes / methods
  - module-scope script blocks
- Inspect call relationships, usages, and task formation reasons
- Run a single-task optimization loop:
  - diff preview
  - pre-validation
  - apply
  - rollback
- Run optimization batches by phase with live status monitoring
- Export all four canvases as `SVG / PNG / JPG`

### Who It Is For

- People who need to understand a Python project before changing it
- People who want to split code-change work into ordered, reviewable tasks
- People building an AI-assisted code operations workflow

### Quick Start

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

### Tests

```bash
python3 -m unittest discover -s tests
```

### LLM Integration (Current)

- Unified config: `bettercode/config/config.yaml` (keyed by `model_id`)
- Unified client factory: `bettercode/llm/factory.py`
- Unified gateway: `bettercode/llm/gateway.py`
- Executor integration:
  - `bettercode/translation_executor.py`
  - `bettercode/optimize_executor.py`

Note: translation and optimization executors now call the shared LLM gateway instead of handling provider HTTP details directly.

### LLM Call Flow (Backend)

1. Executor builds prompt + `messages`
2. Calls `llm.gateway.request_chat_completion(...)`
3. Gateway uses `create_llm_client(model_id)` to select provider client
4. Client calls the cloud model and returns a normalized response
5. Executor keeps existing JSON parsing, safety checks, artifacts, and validation flow

### Model Config and Connectivity Check

```bash
python3 -m bettercode.cli.main config --model <model_id> --provider <provider> --api-key <api_key> [--base-url <url>]
python3 tests/test_llm_client.py --model <model_id> --prompt "connectivity check"
```

### Current Status

- The mainline is now: **project parsing + task graph + optimization loop**
- Translation is still experimental (now on the unified LLM gateway path)
- Validation is still a basic safety net, not a full correctness guarantee
- The system is still mostly based on static analysis
- UI config is still being converged toward the unified LLM config path

### Layout

```text
bettercode/
  app.py
  bettercode/
    cli/
    llm/
    parser.py
    task_graph.py
    task_planner.py
    optimize_executor.py
    translation_executor.py
    ui/
  tests/
```
