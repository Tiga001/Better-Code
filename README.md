# BetterCode

[中文](#中文) | [English](#english)

---

## 中文

### 项目定位

BetterCode 是一个纯 Python + PySide6 的桌面应用，目标不是单纯“画依赖图”，而是逐步发展成一个面向 Python 项目的：

- 代码结构理解平台
- 任务切分与排序平台
- AI 驱动的代码优化 / 代码翻译工作台

当前主线已经聚焦在：

- 解析 Python 项目结构
- 构建文件级与任务级图谱
- 为优化 / 翻译生成任务单元
- 对单任务优化提供预览、验证、应用、回滚闭环
- 对批次优化提供 phase 级监控与执行

### 当前功能

#### 1. 项目解析与图谱

- 导入本地 Python 项目目录
- 解析文件级依赖图
- 识别：
  - 外部包
  - 依赖叶子
  - 内部文件
  - 顶层脚本
- 提供 4 个主视图：
  - 依赖图
  - 子系统
  - 任务图
  - 批次视图

#### 2. 代码块分析

- 提取：
  - 顶层函数
  - 类
  - 方法
  - 顶层脚本块（module scope）
- 展示：
  - 类 / 函数 / 方法结构
  - 调用关系
  - Find Usages / 引用位置
  - 任务形成原因
  - 代码预览

#### 3. 任务切分与排序

- 生成任务图（Task Graph）
- 生成批次图（Batch / Phase View）
- 自动合并循环任务组
- 根据依赖关系生成 phase 顺序
- 区分阻塞依赖与上下文依赖

#### 4. 优化执行器

单任务优化已经支持完整闭环：

1. 生成优化请求
2. 调用兼容 chat-completions 的模型
3. 生成结构化 `edits[]`
4. 本地生成 diff 预览
5. 在隔离工作区预验证
6. 应用 patch 到真实项目
7. 失败时回滚
8. 保留优化历史并可重新打开 diff

#### 5. 批次优化执行

- 支持按 phase 执行优化批次
- 当前 phase 串行执行
- 任一任务失败后阻断后续 phase
- 前端会显示：
  - 当前运行任务
  - 每个任务状态
  - 已完成任务
  - 失败 / 阻断任务
  - 对应 diff 历史入口

#### 6. 导出能力

四张画布都支持导出为：

- SVG
- PNG
- JPG / JPEG

### 技术栈

- Python 3.11+
- PySide6
- Python `ast`

### 安装与运行

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

### 测试

```bash
python3 -m unittest discover -s tests
```

### 使用说明

#### 导入项目

1. 运行应用
2. 点击 `导入项目`
3. 选择一个本地 Python 项目目录

#### 查看代码块

1. 在依赖图或子系统图里双击内部文件节点
2. 打开代码块弹窗
3. 查看：
   - 结构树
   - 调用关系
   - 引用位置
   - 任务候选

#### 单任务优化

1. 切到 `任务图`
2. 点击一个任务节点
3. 在右侧选择 `指派优化任务`
4. 查看 diff 预览
5. 决定是否应用 / 回滚

#### 批次优化

1. 切到 `批次视图`
2. 选择 `Optimize`
3. 点击：
   - `执行当前阶段`
   - 或 `执行整个批次`
4. 在右侧批次监控面板查看状态和历史

### 模型配置

BetterCode 当前支持兼容 chat-completions 的模型接口。

可以通过两种方式提供模型配置：

#### 方式一：主界面配置

- 点击主界面右上角 `API 配置`
- 填写：
  - API URL
  - Model Name
  - API Token
  - Timeout

#### 方式二：环境变量

```bash
export BETTERCODE_MODEL_API_TOKEN="your-token"
export BETTERCODE_MODEL_API_URL="https://your-endpoint.example.com/v1/chat/completions"
export BETTERCODE_MODEL_NAME="your-model-name"
```

说明：

- 不要把真实 token 提交到仓库
- 如果你使用的是中转站，请填写**完整接口地址**，而不是 SDK 的 base URL

### 翻译能力现状

翻译功能当前仍然是实验线。

目前支持：

- 为单个 Python 函数生成翻译任务
- 调用模型生成目标产物
- 将结果写入 `generated/translations/`

当前还**没有完成真正的翻译验证闭环**，例如：

- 自动编译
- 行为等价性对比
- 完整工程级集成验证

### 生成目录

运行过程中，BetterCode 会在项目下生成：

- `generated/optimizations/`
- `generated/translations/`
- `generated/batch_runs/`

这些目录用于保存：

- 请求与响应
- diff
- 验证报告
- 优化历史
- 批次执行报告

### 当前限制

当前版本仍有这些边界：

- 以静态分析为主
- 对 `eval`、`exec`、反射、动态导入这类 Python 动态特性支持有限
- 严格自动化验证仍未完全做完
- 翻译能力还处于实验阶段
- 当前批次执行仅支持优化模式

### 仓库结构

```text
bettercode/
  app.py
  bettercode/
    parser.py
    task_graph.py
    task_planner.py
    optimize_executor.py
    translation_executor.py
    ui/
  tests/
  requirements.txt
```

### 当前阶段的项目目标

BetterCode 目前最核心的方向不是“再做更多前端控件”，而是：

- 提高任务切分与执行的可靠性
- 强化优化验证闭环
- 逐步补全翻译闭环
- 让任务图 / 批次图真正成为 AI 代码处理基础设施

---

## English

### What BetterCode Is

BetterCode is a pure Python + PySide6 desktop application. It is not just a dependency viewer. The long-term goal is to become a Python-focused platform for:

- codebase understanding
- task decomposition and ordering
- AI-assisted optimization and translation workflows

The current product direction focuses on:

- parsing Python project structure
- building file-level and task-level graphs
- generating executable task units for optimization / translation
- providing a full single-task optimization loop
- providing phase-based monitoring and execution for batch optimization

### Current Capabilities

#### 1. Project Parsing and Graph Views

- Import a local Python project
- Build a file-level dependency graph
- Classify:
  - external packages
  - dependency leaves
  - internal files
  - top-level scripts
- Provide 4 primary graph modes:
  - Dependency Graph
  - Subsystems
  - Task Graph
  - Batch / Phase View

#### 2. Code Block Analysis

- Extract:
  - top-level functions
  - classes
  - methods
  - module-scope script blocks
- Display:
  - block tree
  - call relationships
  - Find Usages
  - task formation reasons
  - source preview

#### 3. Task Planning and Ordering

- Build a task graph
- Build a phase / batch plan
- Merge cyclic units into cycle groups
- Order tasks by dependency depth
- Separate blocking dependencies from context-only dependencies

#### 4. Optimization Executor

Single-task optimization already supports a full workflow:

1. build optimization request
2. call a chat-completions compatible model
3. receive structured `edits[]`
4. generate a local diff preview
5. run pre-validation in an isolated workspace
6. apply the patch to the live project
7. roll back if needed
8. keep optimization history and reopen previous diffs

#### 5. Batch Optimization

- Run optimization by phase
- Current implementation runs serially inside each phase
- Any failed task blocks later phases
- The UI shows:
  - current running task
  - per-task execution state
  - completed tasks
  - failed / blocked tasks
  - reopenable diff history

#### 6. Export

All four canvases can be exported as:

- SVG
- PNG
- JPG / JPEG

### Stack

- Python 3.11+
- PySide6
- Python `ast`

### Install and Run

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

### Tests

```bash
python3 -m unittest discover -s tests
```

### Basic Workflow

#### Import a Project

1. Launch the app
2. Click `Import Project`
3. Select a local Python project directory

#### Inspect Code Blocks

1. Double-click an internal file node in the dependency graph or subsystem view
2. Open the code-block dialog
3. Inspect:
   - structure tree
   - call relationships
   - usages
   - task candidates

#### Run a Single Optimization Task

1. Switch to `Task Graph`
2. Select a task node
3. Use `Assign Optimize Task`
4. Review the diff
5. Decide whether to apply or roll back

#### Run a Batch Optimization

1. Switch to `Batch View`
2. Choose `Optimize`
3. Click:
   - `Run Current Phase`
   - or `Run Whole Batch`
4. Watch progress from the batch monitor panel

### Model Configuration

BetterCode currently supports chat-completions compatible model APIs.

You can configure the model in two ways:

#### Option 1: UI Configuration

- Click `API Config` in the top-right area of the main window
- Fill in:
  - API URL
  - Model Name
  - API Token
  - Timeout

#### Option 2: Environment Variables

```bash
export BETTERCODE_MODEL_API_TOKEN="your-token"
export BETTERCODE_MODEL_API_URL="https://your-endpoint.example.com/v1/chat/completions"
export BETTERCODE_MODEL_NAME="your-model-name"
```

Notes:

- Do not commit real API tokens into the repository
- If you use a relay/proxy service, provide the **full endpoint URL**, not only an SDK-style base URL

### Translation Status

Translation is still an experimental track.

It currently supports:

- generating translation tasks for individual Python functions
- calling a model to produce translation artifacts
- saving outputs under `generated/translations/`

It does **not** yet provide a complete verification loop such as:

- automatic compilation
- behavior equivalence checks
- full project-level translation validation

### Generated Output

BetterCode writes execution artifacts into:

- `generated/optimizations/`
- `generated/translations/`
- `generated/batch_runs/`

These folders store:

- requests and responses
- diffs
- validation reports
- optimization history
- batch execution reports

### Current Limitations

Current boundaries include:

- mostly static analysis
- limited support for highly dynamic Python behavior such as `eval`, `exec`, reflection, and dynamic imports
- strict automated validation is still incomplete
- translation is still experimental
- batch execution currently supports optimization mode only

### Repository Layout

```text
bettercode/
  app.py
  bettercode/
    parser.py
    task_graph.py
    task_planner.py
    optimize_executor.py
    translation_executor.py
    ui/
  tests/
  requirements.txt
```

### Project Direction

The main value of BetterCode is no longer “more UI controls”. The real direction is:

- improve task decomposition and execution reliability
- strengthen the optimization verification loop
- gradually complete the translation verification loop
- make the task graph / batch graph a real AI code operation infrastructure layer
