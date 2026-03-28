# bettercode_agent_api

这是一个从 BetterCode 里拆出来的、**只负责解析 Python 项目结构**的小包。

它不会启动 BetterCode 界面，也不会调用大模型。  
它做的事很单纯：

- 读一个 Python 项目目录
- 解析项目结构
- 返回 4 份 JSON 结构数据：
  - `dependency_graph`
  - `subsystem_graph`
  - `task_graph`
  - `batch_view`

## 适合谁用

适合想在自己的 agent / workflow / 子进程里直接调用的人。

如果你只是想拿到结构化分析结果，不想接 BetterCode 前端，这个包就是给你用的。

## 依赖

这个包只用 Python 标准库。  
一般不用额外安装第三方依赖。

## 最快用法

### Python 里直接调

```python
from bettercode_agent_api import analyze_project_for_agent

result = analyze_project_for_agent("/path/to/python/project")
print(result["project_name"])
print(result["task_graph"]["graph"]["units"][:3])
```

### 命令行调用

```bash
python -m bettercode_agent_api /path/to/python/project
```

如果你想让输出更紧凑，方便别的程序读取：

```bash
python -m bettercode_agent_api /path/to/python/project --compact
```

## 返回结果里有什么

顶层会返回这些字段：

```json
{
  "schema_version": "1.0",
  "analysis_mode": "static",
  "generated_at": "...",
  "project_root": "...",
  "project_name": "...",
  "issues": { ... },
  "dependency_graph": { ... },
  "subsystem_graph": { ... },
  "task_graph": { ... },
  "batch_view": { ... }
}
```

如果你想看每个字段的详细定义，直接看同目录外附带的：

- `AGENT_API_SCHEMA.md`

## 这 4 份结构数据分别是什么

### 1. dependency_graph
文件级依赖图。

你可以拿到：
- 项目里的文件节点
- 第三方库节点
- import 边
- 每个文件的类、函数、代码块、调用、usage 摘要

### 2. subsystem_graph
项目按连通关系拆出来的子系统。

你可以拿到：
- 每个子系统包含哪些文件
- 子系统内部有哪些边
- 哪些是入口节点
- 哪些是叶子节点

### 3. task_graph
把代码块进一步整理成任务单元后的 DAG。

你可以拿到：
- 任务节点
- 任务依赖边
- 边的类型
  - `strong_call`
  - `inheritance`
  - `import_only`
- optimize / translate 的执行顺序

### 4. batch_view
按 phase 分组后的执行视图。

你可以拿到：
- optimize 批次
- translate 批次
- 每个 phase 里有哪些任务

## 限制

这是静态分析，不是运行时分析。  
下面这些场景不保证精准：

- 动态导入
- `eval`
- `exec`
- `getattr` / `setattr`
- monkey patch
- 运行时分发

## 给协作者的建议

如果你准备把这个包接进 agent loop，建议：

1. 先调一次命令行版，确认输出结构符合预期
2. 再在 Python 里直接 import
3. 解析时优先看：
   - `issues`
   - `task_graph`
   - `batch_view`

通常最有用的是：
- `issues.syntax_errors`
- `task_graph.graph.units`
- `task_graph.plans.optimize`
- `batch_view.optimize.phases`

## 一句话总结

这个包就是：

**把一个 Python 项目目录，变成适合 agent 直接消费的结构化 JSON。**
