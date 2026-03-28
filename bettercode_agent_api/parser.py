from __future__ import annotations

import ast
import importlib.util
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from bettercode_agent_api.models import (
    AgentTaskSuitability,
    ClassSummary,
    CodeBlockCall,
    CodeBlockKind,
    CodeBlockSummary,
    FileDetail,
    FunctionSummary,
    GraphEdge,
    GraphNode,
    ImportKind,
    ImportRecord,
    NodeKind,
    ProjectGraph,
    ProjectSummary,
    SymbolUsage,
    UsageConfidence,
    UsageKind,
)

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "generated",
    "node_modules",
    "site-packages",
    "venv",
}
SOURCE_ROOT_DIRS = ("src", "python", "lib")
SOURCE_PREVIEW_MAX_LINES = 180
SOURCE_PREVIEW_MAX_CHARS = 12000
STANDARD_LIBRARY_MODULES = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}


@dataclass(slots=True)
class _RawCodeBlockCall:
    source_id: str | None
    source_node_id: str
    line: int
    expression: str
    func_node: ast.AST


@dataclass(slots=True)
class _RawInstanceBinding:
    block_id: str | None
    block_node_id: str
    line: int
    variable_name: str
    constructor_node: ast.AST
    constructor_expression: str


@dataclass(slots=True)
class _RawSymbolUsage:
    source_node_id: str
    line: int
    expression: str
    usage_kind: UsageKind
    owner_block_id: str | None = None
    symbol_name: str | None = None
    attribute_chain: tuple[str, ...] | None = None
    import_module: str | None = None
    import_name: str | None = None
    import_level: int = 0


@dataclass(slots=True)
class _ProjectCallContext:
    node_id: str
    module_name: str
    file_path: Path
    parsed_tree: ast.Module
    raw_calls: list[_RawCodeBlockCall]
    raw_instance_bindings: list[_RawInstanceBinding]
    raw_symbol_usages: list[_RawSymbolUsage]
    module_aliases: dict[str, str]
    symbol_aliases: dict[str, tuple[str, str]]
    scoped_symbol_aliases: dict[str | None, dict[str, tuple[str, str]]]
    star_import_modules: tuple[str, ...]


class _ReturnCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.values: list[ast.AST | None] = []

    def visit_Return(self, node: ast.Return) -> None:  # type: ignore[override]
        self.values.append(node.value)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # type: ignore[override]
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # type: ignore[override]
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # type: ignore[override]
        return


class _CodeBlockExtractor(ast.NodeVisitor):
    def __init__(self, *, node_id: str) -> None:
        self.blocks: list[CodeBlockSummary] = []
        self.calls: list[CodeBlockCall] = []
        self._stack: list[CodeBlockSummary] = []
        self._sequence = 0
        self._module_scope_sequence = 0
        self._raw_calls: list[_RawCodeBlockCall] = []
        self._raw_instance_bindings: list[_RawInstanceBinding] = []
        self._raw_symbol_usages: list[_RawSymbolUsage] = []
        self._node_id = node_id

    def visit_Module(self, node: ast.Module) -> None:  # type: ignore[override]
        module_scope_group: list[ast.stmt] = []
        for statement in node.body:
            if self._is_module_scope_executable_statement(statement):
                module_scope_group.append(statement)
                continue
            self._visit_module_scope_group(module_scope_group)
            module_scope_group = []
            self.visit(statement)
        self._visit_module_scope_group(module_scope_group)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # type: ignore[override]
        block = self._push_block(
            kind=CodeBlockKind.CLASS,
            name=node.name,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            signature=self._class_signature(node),
            parameters=[],
            return_summary=None,
        )
        for base in node.bases:
            self._record_symbol_usages_from_expr(
                base,
                usage_kind=UsageKind.INHERITANCE,
                owner_block_id=block.id,
                line=getattr(base, "lineno", node.lineno),
            )
        for decorator in node.decorator_list:
            self._record_symbol_usages_from_expr(
                self._decorator_target(decorator),
                usage_kind=UsageKind.DECORATOR,
                owner_block_id=block.id,
                line=getattr(decorator, "lineno", node.lineno),
            )
        for child in node.body:
            self.visit(child)
        self._pop_block(block.id)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # type: ignore[override]
        self._visit_function_like(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # type: ignore[override]
        self._visit_function_like(node)

    def _visit_function_like(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        parent = self._stack[-1] if self._stack else None
        kind = CodeBlockKind.METHOD if parent and parent.kind is CodeBlockKind.CLASS else CodeBlockKind.FUNCTION
        block = self._push_block(
            kind=kind,
            name=node.name,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            signature=self._function_signature(node),
            parameters=self._parameter_summary(node, kind),
            return_summary=self._return_summary(node),
        )
        for decorator in node.decorator_list:
            self._record_symbol_usages_from_expr(
                self._decorator_target(decorator),
                usage_kind=UsageKind.DECORATOR,
                owner_block_id=block.id,
                line=getattr(decorator, "lineno", node.lineno),
            )
        self._record_function_annotation_usages(node, block.id)
        for child in node.body:
            self.visit(child)
        self._pop_block(block.id)

    def _visit_module_scope_group(self, statements: list[ast.stmt]) -> None:
        if not statements:
            return
        self._module_scope_sequence += 1
        first_statement = statements[0]
        last_statement = statements[-1]
        block = self._push_block(
            kind=CodeBlockKind.MODULE_SCOPE,
            name=f"module_scope_{self._module_scope_sequence}",
            line=getattr(first_statement, "lineno", 1),
            end_line=getattr(last_statement, "end_lineno", getattr(first_statement, "lineno", 1)),
            signature=f"module scope #{self._module_scope_sequence}",
            parameters=[],
            return_summary=None,
        )
        for statement in statements:
            self.visit(statement)
        self._pop_block(block.id)

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        current_block = self._stack[-1] if self._stack else None
        self._raw_calls.append(
            _RawCodeBlockCall(
                source_id=current_block.id if current_block is not None else None,
                source_node_id=self._node_id,
                line=getattr(node, "lineno", current_block.line if current_block is not None else 0),
                expression=self._expression_text(node.func),
                func_node=node.func,
            )
        )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # type: ignore[override]
        self._record_instance_binding(node.targets, node.value, getattr(node, "lineno", 0))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # type: ignore[override]
        self._record_instance_binding([node.target], node.value, getattr(node, "lineno", 0))
        if node.annotation is not None:
            self._record_symbol_usages_from_expr(
                node.annotation,
                usage_kind=UsageKind.TYPE_ANNOTATION,
                owner_block_id=self._current_owner_block_id(),
                line=getattr(node.annotation, "lineno", getattr(node, "lineno", 0)),
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # type: ignore[override]
        for alias in node.names:
            if alias.name == "*":
                continue
            expression = f"{node.module}.{alias.name}" if node.module else alias.name
            self._raw_symbol_usages.append(
                _RawSymbolUsage(
                    source_node_id=self._node_id,
                    owner_block_id=self._current_owner_block_id(),
                    line=node.lineno,
                    expression=expression,
                    usage_kind=UsageKind.IMPORT,
                    import_module=node.module,
                    import_name=alias.name,
                    import_level=node.level,
                    symbol_name=alias.asname or alias.name,
                )
            )
        self.generic_visit(node)

    def _push_block(
        self,
        *,
        kind: CodeBlockKind,
        name: str,
        line: int,
        end_line: int,
        signature: str,
        parameters: list[str],
        return_summary: str | None,
    ) -> CodeBlockSummary:
        block = CodeBlockSummary(
            id=f"{self._node_id}#block:{self._sequence}",
            kind=kind,
            name=name,
            line=line,
            end_line=end_line,
            depth=len(self._stack),
            parent_id=self._stack[-1].id if self._stack else None,
            signature=signature,
            parameters=parameters,
            return_summary=return_summary,
        )
        self._sequence += 1
        self.blocks.append(block)
        self._stack.append(block)
        return block

    def _is_module_scope_executable_statement(self, statement: ast.stmt) -> bool:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            return False
        if isinstance(statement, ast.Expr):
            return not self._is_simple_declarative_expression(statement.value)
        if isinstance(statement, ast.Assign):
            return not self._is_simple_declarative_expression(statement.value)
        if isinstance(statement, ast.AnnAssign):
            return statement.value is not None and not self._is_simple_declarative_expression(statement.value)
        if isinstance(statement, ast.AugAssign):
            return True
        if isinstance(statement, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match)):
            return True
        if isinstance(statement, (ast.Assert, ast.Raise, ast.Delete)):
            return True
        return False

    def _is_simple_declarative_expression(self, expression: ast.AST | None) -> bool:
        if expression is None:
            return True
        if isinstance(expression, (ast.Constant, ast.Name)):
            return True
        if isinstance(expression, ast.Attribute):
            return self._is_simple_declarative_expression(expression.value)
        if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
            return all(self._is_simple_declarative_expression(element) for element in expression.elts)
        if isinstance(expression, ast.Dict):
            return all(
                self._is_simple_declarative_expression(candidate)
                for candidate in [*expression.keys, *expression.values]
                if candidate is not None
            )
        return False

    def _pop_block(self, block_id: str) -> None:
        if self._stack and self._stack[-1].id == block_id:
            self._stack.pop()

    def _class_signature(self, node: ast.ClassDef) -> str:
        if not node.bases:
            return f"class {node.name}"
        bases = ", ".join(self._expr_name(base) for base in node.bases[:3])
        if len(node.bases) > 3:
            bases = f"{bases}, ..."
        return f"class {node.name}({bases})"

    def _function_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        positional = [argument.arg for argument in node.args.posonlyargs + node.args.args]
        parts = positional[:]
        if node.args.vararg:
            parts.append(f"*{node.args.vararg.arg}")
        elif node.args.kwonlyargs:
            parts.append("*")
        parts.extend(argument.arg for argument in node.args.kwonlyargs)
        if node.args.kwarg:
            parts.append(f"**{node.args.kwarg.arg}")
        if len(parts) > 5:
            parts = parts[:5] + ["..."]
        prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        return f"{prefix}{node.name}({', '.join(parts)})"

    def _parameter_summary(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        kind: CodeBlockKind,
    ) -> list[str]:
        parameters: list[str] = []
        positional_args = node.args.posonlyargs + node.args.args
        positional_defaults = [None] * (len(positional_args) - len(node.args.defaults)) + list(node.args.defaults)

        for index, (argument, default) in enumerate(zip(positional_args, positional_defaults)):
            if kind is CodeBlockKind.METHOD and index == 0 and argument.arg in {"self", "cls"}:
                continue
            parameters.append(self._argument_summary(argument, default))

        if node.args.vararg:
            parameters.append(self._argument_summary(node.args.vararg, prefix="*"))
        elif node.args.kwonlyargs:
            parameters.append("*")

        for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            parameters.append(self._argument_summary(argument, default))

        if node.args.kwarg:
            parameters.append(self._argument_summary(node.args.kwarg, prefix="**"))
        return parameters

    def _argument_summary(
        self,
        argument: ast.arg,
        default: ast.AST | None = None,
        *,
        prefix: str = "",
    ) -> str:
        summary = f"{prefix}{argument.arg}"
        if argument.annotation is not None:
            summary = f"{summary}: {self._expression_text(argument.annotation)}"
        if default is not None:
            summary = f"{summary} = {self._expression_text(default)}"
        return summary

    def _return_summary(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        if node.returns is not None:
            return self._expression_text(node.returns)

        collector = _ReturnCollector()
        for statement in node.body:
            collector.visit(statement)

        if not collector.values:
            return "None"

        unique_summaries: list[str] = []
        for value in collector.values:
            summary = self._return_value_summary(value)
            if summary not in unique_summaries:
                unique_summaries.append(summary)

        if len(unique_summaries) <= 3:
            return " | ".join(unique_summaries)
        return " | ".join(unique_summaries[:3]) + " | ..."

    def _return_value_summary(self, value: ast.AST | None) -> str:
        if value is None:
            return "None"
        if isinstance(value, ast.Constant):
            return type(value.value).__name__ if value.value is not None else "None"
        if isinstance(value, ast.List):
            return "list"
        if isinstance(value, ast.Tuple):
            return "tuple"
        if isinstance(value, ast.Dict):
            return "dict"
        if isinstance(value, ast.Set):
            return "set"
        if isinstance(value, ast.Name):
            return f"value: {value.id}"
        if isinstance(value, ast.Call):
            return f"result of {self._expression_text(value.func)}"
        return self._expression_text(value)

    def finalize(
        self,
    ) -> tuple[
        list[CodeBlockSummary],
        list[CodeBlockCall],
        list[_RawCodeBlockCall],
        list[_RawInstanceBinding],
        list[_RawSymbolUsage],
    ]:
        self.calls = self._resolve_calls()
        return self.blocks, self.calls, self._raw_calls, self._raw_instance_bindings, self._raw_symbol_usages

    def _resolve_calls(self) -> list[CodeBlockCall]:
        blocks_by_id = {block.id: block for block in self.blocks}
        top_level_by_name: dict[str, list[str]] = {}
        child_blocks: dict[str, list[str]] = {}
        methods_by_class: dict[str, dict[str, list[str]]] = {}
        class_ids_by_name: dict[str, list[str]] = {}
        instance_bindings_by_block: dict[str, list[_RawInstanceBinding]] = {}

        for block in self.blocks:
            if block.parent_id is None:
                if block.kind in {CodeBlockKind.CLASS, CodeBlockKind.FUNCTION}:
                    top_level_by_name.setdefault(block.name, []).append(block.id)
            else:
                child_blocks.setdefault(block.parent_id, []).append(block.id)
                parent_block = blocks_by_id[block.parent_id]
                if parent_block.kind is CodeBlockKind.CLASS and block.kind is CodeBlockKind.METHOD:
                    methods_by_class.setdefault(parent_block.id, {}).setdefault(block.name, []).append(block.id)
            if block.kind is CodeBlockKind.CLASS:
                class_ids_by_name.setdefault(block.name, []).append(block.id)

        for binding in self._raw_instance_bindings:
            instance_bindings_by_block.setdefault(binding.block_id, []).append(binding)

        for block_id in instance_bindings_by_block:
            instance_bindings_by_block[block_id].sort(key=lambda binding: binding.line)

        call_edges: list[CodeBlockCall] = []
        seen_edges: set[tuple[str, str, int]] = set()
        for raw_call in self._raw_calls:
            if raw_call.source_id is None:
                continue
            target_id = self._resolve_call_target(
                raw_call=raw_call,
                blocks_by_id=blocks_by_id,
                top_level_by_name=top_level_by_name,
                child_blocks=child_blocks,
                methods_by_class=methods_by_class,
                class_ids_by_name=class_ids_by_name,
                instance_bindings_by_block=instance_bindings_by_block,
            )
            if target_id is None:
                continue
            edge_key = (raw_call.source_id, target_id, raw_call.line)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            call_edges.append(
                CodeBlockCall(
                    source_id=raw_call.source_id,
                    source_node_id=self._node_id,
                    target_id=target_id,
                    target_node_id=target_id.split("#block:", 1)[0],
                    line=raw_call.line,
                    expression=raw_call.expression,
                    is_cross_file=False,
                )
            )

        call_edges.sort(key=lambda edge: (edge.source_id, edge.line, edge.target_id))
        return call_edges

    def _resolve_call_target(
        self,
        *,
        raw_call: _RawCodeBlockCall,
        blocks_by_id: dict[str, CodeBlockSummary],
        top_level_by_name: dict[str, list[str]],
        child_blocks: dict[str, list[str]],
        methods_by_class: dict[str, dict[str, list[str]]],
        class_ids_by_name: dict[str, list[str]],
        instance_bindings_by_block: dict[str, list[_RawInstanceBinding]],
    ) -> str | None:
        source_block = blocks_by_id.get(raw_call.source_id)
        if source_block is None:
            return None

        func_node = raw_call.func_node
        if isinstance(func_node, ast.Name):
            direct_children = child_blocks.get(source_block.id, [])
            for child_id in direct_children:
                child_block = blocks_by_id[child_id]
                if child_block.name == func_node.id:
                    return child_block.id
            return self._first_id(top_level_by_name.get(func_node.id, []))

        if isinstance(func_node, ast.Attribute):
            containing_class_id = self._containing_class_id(source_block.id, blocks_by_id)
            if isinstance(func_node.value, ast.Name):
                if func_node.value.id in {"self", "cls"} and containing_class_id is not None:
                    return self._first_method_id(methods_by_class, containing_class_id, func_node.attr)
                class_id = self._first_id(class_ids_by_name.get(func_node.value.id, []))
                if class_id is not None:
                    return self._first_method_id(methods_by_class, class_id, func_node.attr)
                bound_class = self._bound_class_name(
                    block_id=source_block.id,
                    variable_name=func_node.value.id,
                    call_line=raw_call.line,
                    instance_bindings_by_block=instance_bindings_by_block,
                )
                if bound_class is not None:
                    class_id = self._first_id(class_ids_by_name.get(bound_class, []))
                    if class_id is not None:
                        return self._first_method_id(methods_by_class, class_id, func_node.attr)

            if isinstance(func_node.value, ast.Call) and isinstance(func_node.value.func, ast.Name):
                class_id = self._first_id(class_ids_by_name.get(func_node.value.func.id, []))
                if class_id is not None:
                    return self._first_method_id(methods_by_class, class_id, func_node.attr)

        return None

    def _containing_class_id(
        self,
        block_id: str,
        blocks_by_id: dict[str, CodeBlockSummary],
    ) -> str | None:
        current_id = block_id
        while current_id:
            block = blocks_by_id[current_id]
            if block.kind is CodeBlockKind.CLASS:
                return block.id
            current_id = block.parent_id or ""
        return None

    def _first_method_id(
        self,
        methods_by_class: dict[str, dict[str, list[str]]],
        class_id: str,
        method_name: str,
    ) -> str | None:
        return self._first_id(methods_by_class.get(class_id, {}).get(method_name, []))

    def _first_id(self, identifiers: list[str]) -> str | None:
        return identifiers[0] if identifiers else None

    def _bound_class_name(
        self,
        *,
        block_id: str,
        variable_name: str,
        call_line: int,
        instance_bindings_by_block: dict[str, list[_RawInstanceBinding]],
    ) -> str | None:
        latest_class_name: str | None = None
        for binding in instance_bindings_by_block.get(block_id, []):
            if binding.variable_name != variable_name or binding.line > call_line:
                continue
            if isinstance(binding.constructor_node, ast.Name):
                latest_class_name = binding.constructor_node.id
        return latest_class_name

    def _apply_agent_task_fit(self) -> None:
        children_by_parent: dict[str, list[CodeBlockSummary]] = {}
        outgoing: dict[str, list[CodeBlockCall]] = {}
        incoming: dict[str, list[CodeBlockCall]] = {}
        blocks_by_id = {block.id: block for block in self.blocks}

        for block in self.blocks:
            if block.parent_id is not None:
                children_by_parent.setdefault(block.parent_id, []).append(block)
            outgoing.setdefault(block.id, [])
            incoming.setdefault(block.id, [])

        for call in self.calls:
            outgoing.setdefault(call.source_id, []).append(call)
            incoming.setdefault(call.target_id, []).append(call)

        for block in self.blocks:
            line_span = max(block.end_line - block.line + 1, 1)
            child_count = len(children_by_parent.get(block.id, []))
            outgoing_count = len(outgoing.get(block.id, []))
            incoming_count = len(incoming.get(block.id, []))
            fit, reasons = self._task_fit_for_block(
                block=block,
                line_span=line_span,
                child_count=child_count,
                outgoing_count=outgoing_count,
                incoming_count=incoming_count,
                blocks_by_id=blocks_by_id,
            )
            block.agent_task_fit = fit
            block.agent_task_reasons = reasons

    def _task_fit_for_block(
        self,
        *,
        block: CodeBlockSummary,
        line_span: int,
        child_count: int,
        outgoing_count: int,
        incoming_count: int,
        blocks_by_id: dict[str, CodeBlockSummary],
    ) -> tuple[AgentTaskSuitability, list[str]]:
        reasons: list[str] = []

        if block.kind is CodeBlockKind.MODULE_SCOPE:
            reasons.append("module-scope execution usually needs file-level context")
            if line_span > 80 or outgoing_count > 4 or child_count > 0:
                reasons.append("module-scope block is large or fans out too widely")
                return AgentTaskSuitability.AVOID, reasons
            if incoming_count:
                reasons.append(f"referenced by {incoming_count} block(s)")
            reasons.append("script-style work can be handled, but keep surrounding setup visible")
            return AgentTaskSuitability.CAUTION, reasons

        if block.kind is CodeBlockKind.CLASS:
            reasons.append(f"{child_count} direct child blocks")
            if line_span > 140 or child_count > 6:
                reasons.append("class is large enough that it should be split before agent work")
                return AgentTaskSuitability.AVOID, reasons
            reasons.append("class work usually needs shared state and method context")
            return AgentTaskSuitability.CAUTION, reasons

        if block.parent_id and blocks_by_id[block.parent_id].kind is CodeBlockKind.CLASS:
            if block.name.startswith("__") and block.name.endswith("__"):
                reasons.append("dunder methods are tightly coupled to class behavior")
                return AgentTaskSuitability.AVOID, reasons
            if block.name.startswith("_"):
                reasons.append("private methods are usually implementation details of the class")
            else:
                reasons.append("method changes still need surrounding class context")
            if line_span > 50 or outgoing_count > 2:
                reasons.append("method has enough local coupling that a wider task is safer")
                return AgentTaskSuitability.AVOID, reasons
            reasons.append("small method can be handed off with class context attached")
            return AgentTaskSuitability.CAUTION, reasons

        if block.depth > 0:
            reasons.append("nested blocks depend on enclosing scope")
            if line_span > 40 or outgoing_count > 1:
                reasons.append("nested block is not isolated enough for a standalone task")
                return AgentTaskSuitability.AVOID, reasons
            return AgentTaskSuitability.CAUTION, reasons

        if line_span <= 35 and outgoing_count <= 2 and child_count == 0:
            reasons.append("small top-level block with limited same-file coupling")
            if incoming_count:
                reasons.append(f"called by {incoming_count} same-file block(s)")
            return AgentTaskSuitability.GOOD, reasons

        if line_span > 100 or outgoing_count > 4 or child_count > 1:
            reasons.append("block is large or fans out to many sibling blocks")
            return AgentTaskSuitability.AVOID, reasons

        reasons.append("top-level block is workable but still needs nearby context")
        if outgoing_count:
            reasons.append(f"depends on {outgoing_count} same-file block(s)")
        return AgentTaskSuitability.CAUTION, reasons

    def _expression_text(self, node: ast.AST) -> str:
        try:
            text = ast.unparse(node)
        except Exception:  # pragma: no cover
            return "..."
        if len(text) <= 48:
            return text
        return f"{text[:45]}..."

    def _record_instance_binding(
        self,
        targets: list[ast.expr],
        value: ast.AST | None,
        line: int,
    ) -> None:
        if not isinstance(value, ast.Call):
            return
        current_block = self._stack[-1] if self._stack else None
        for target in targets:
            for variable_name in self._target_names(target):
                self._raw_instance_bindings.append(
                    _RawInstanceBinding(
                        block_id=current_block.id if current_block is not None else None,
                        block_node_id=self._node_id,
                        line=line,
                        variable_name=variable_name,
                        constructor_node=value.func,
                        constructor_expression=self._expression_text(value.func),
                    )
                )

    def _record_function_annotation_usages(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        owner_block_id: str,
    ) -> None:
        for argument in (
            node.args.posonlyargs
            + node.args.args
            + node.args.kwonlyargs
            + ([node.args.vararg] if node.args.vararg else [])
            + ([node.args.kwarg] if node.args.kwarg else [])
        ):
            if argument is None or argument.annotation is None:
                continue
            self._record_symbol_usages_from_expr(
                argument.annotation,
                usage_kind=UsageKind.TYPE_ANNOTATION,
                owner_block_id=owner_block_id,
                line=getattr(argument.annotation, "lineno", node.lineno),
            )
        if node.returns is not None:
            self._record_symbol_usages_from_expr(
                node.returns,
                usage_kind=UsageKind.TYPE_ANNOTATION,
                owner_block_id=owner_block_id,
                line=getattr(node.returns, "lineno", node.lineno),
            )

    def _record_symbol_usages_from_expr(
        self,
        expression: ast.AST | None,
        *,
        usage_kind: UsageKind,
        owner_block_id: str | None,
        line: int,
    ) -> None:
        if expression is None:
            return
        for candidate in self._reference_candidates(expression):
            attribute_chain = self._attribute_chain(candidate) if isinstance(candidate, ast.Attribute) else None
            self._raw_symbol_usages.append(
                _RawSymbolUsage(
                    source_node_id=self._node_id,
                    owner_block_id=owner_block_id,
                    line=line,
                    expression=self._expression_text(candidate),
                    usage_kind=usage_kind,
                    symbol_name=candidate.id if isinstance(candidate, ast.Name) else None,
                    attribute_chain=tuple(attribute_chain) if attribute_chain is not None else None,
                )
            )

    def _reference_candidates(self, node: ast.AST) -> list[ast.AST]:
        candidates: list[ast.AST] = []

        def visit(current: ast.AST | None) -> None:
            if current is None:
                return
            if isinstance(current, ast.Name):
                candidates.append(current)
                return
            if isinstance(current, ast.Attribute):
                if self._attribute_chain(current) is not None:
                    candidates.append(current)
                return
            if isinstance(current, ast.Call):
                visit(current.func)
                return
            if isinstance(current, ast.Subscript):
                visit(current.value)
                visit(current.slice)
                return
            if isinstance(current, ast.BinOp):
                visit(current.left)
                visit(current.right)
                return
            if isinstance(current, (ast.Tuple, ast.List, ast.Set)):
                for element in current.elts:
                    visit(element)
                return
            if isinstance(current, ast.Dict):
                for key in current.keys:
                    visit(key)
                for value in current.values:
                    visit(value)
                return
            if isinstance(current, ast.UnaryOp):
                visit(current.operand)
                return
            if isinstance(current, ast.BoolOp):
                for value in current.values:
                    visit(value)
                return
            if isinstance(current, ast.IfExp):
                visit(current.body)
                visit(current.orelse)
                return

        visit(node)
        return candidates

    def _decorator_target(self, decorator: ast.AST) -> ast.AST:
        if isinstance(decorator, ast.Call):
            return decorator.func
        return decorator

    def _current_owner_block_id(self) -> str | None:
        return self._stack[-1].id if self._stack else None

    def _attribute_chain(self, node: ast.AST) -> list[str] | None:
        parts: list[str] = []
        current: ast.AST | None = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        parts.append(current.id)
        parts.reverse()
        return parts

    def _target_names(self, target: ast.expr) -> list[str]:
        if isinstance(target, ast.Name):
            return [target.id]
        if isinstance(target, (ast.Tuple, ast.List)):
            names: list[str] = []
            for element in target.elts:
                names.extend(self._target_names(element))
            return names
        return []

    def _expr_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._expr_name(node.value)}.{node.attr}"
        return "..."


class ProjectAnalyzer:
    def __init__(self) -> None:
        self._installed_module_cache: dict[str, bool] = {}

    def analyze(self, project_path: str | Path) -> ProjectGraph:
        started_at = time.perf_counter()
        root_path = Path(project_path).expanduser().resolve()
        python_files = self._discover_python_files(root_path)
        source_roots = self._discover_source_roots(root_path)
        module_index = {
            self._module_name_for_path(root_path, file_path, source_roots): file_path for file_path in python_files
        }

        nodes_by_id: dict[str, GraphNode] = {}
        edges_by_key: dict[tuple[str, str], GraphEdge] = {}
        file_details: dict[str, FileDetail] = {}
        call_contexts: dict[str, _ProjectCallContext] = {}
        parse_errors = 0

        for file_path in python_files:
            relative_path = file_path.relative_to(root_path)
            node_id = self._file_node_id(relative_path)
            source = self._load_source(file_path)
            module_name = self._module_name_for_path(root_path, file_path, source_roots)

            try:
                parsed_tree = ast.parse(source, filename=str(file_path))
                syntax_error = None
            except SyntaxError as error:
                parsed_tree = None
                syntax_error = f"{error.msg} (line {error.lineno})"
                parse_errors += 1

            nodes_by_id[node_id] = GraphNode(
                id=node_id,
                kind=NodeKind.PYTHON_FILE,
                label=relative_path.name,
                path=str(relative_path),
                module=module_name,
                metadata={},
            )

            if parsed_tree is None:
                file_details[node_id] = FileDetail(
                    node_id=node_id,
                    path=str(relative_path),
                    module=module_name,
                    imports=[],
                    classes=[],
                    functions=[],
                    code_blocks=[],
                    code_block_calls=[],
                    symbol_usages=[],
                    source_preview=self._summarize_source(source),
                    syntax_error=syntax_error,
                )
                continue

            import_records = self._analyze_imports(
                root_path=root_path,
                file_path=file_path,
                module_name=module_name,
                parsed_tree=parsed_tree,
                module_index=module_index,
            )
            classes = self._extract_classes(parsed_tree)
            functions = self._extract_functions(parsed_tree)
            (
                code_blocks,
                code_block_calls,
                raw_calls,
                raw_instance_bindings,
                raw_symbol_usages,
            ) = self._extract_code_blocks(
                parsed_tree,
                node_id=node_id,
            )
            module_aliases, symbol_aliases, star_import_modules = self._collect_import_bindings(
                parsed_tree=parsed_tree,
                module_name=module_name,
                file_path=file_path,
                module_index=module_index,
            )
            scoped_symbol_aliases = self._collect_scoped_symbol_aliases(
                raw_symbol_usages=raw_symbol_usages,
                module_name=module_name,
                file_path=file_path,
                module_index=module_index,
            )
            call_contexts[node_id] = _ProjectCallContext(
                node_id=node_id,
                module_name=module_name,
                file_path=file_path,
                parsed_tree=parsed_tree,
                raw_calls=raw_calls,
                raw_instance_bindings=raw_instance_bindings,
                raw_symbol_usages=raw_symbol_usages,
                module_aliases=module_aliases,
                symbol_aliases=symbol_aliases,
                scoped_symbol_aliases=scoped_symbol_aliases,
                star_import_modules=star_import_modules,
            )

            for import_record in import_records:
                if import_record.kind is ImportKind.EXTERNAL and import_record.target_node_id:
                    external_id = import_record.target_node_id
                    if external_id not in nodes_by_id:
                        package_name = import_record.module.split(".", 1)[0]
                        nodes_by_id[external_id] = GraphNode(
                            id=external_id,
                            kind=NodeKind.EXTERNAL_PACKAGE,
                            label=package_name,
                        )

                if import_record.target_node_id:
                    edge_key = (node_id, import_record.target_node_id)
                    if edge_key not in edges_by_key:
                        edges_by_key[edge_key] = GraphEdge(
                            id=f"edge:{node_id}->{import_record.target_node_id}",
                            source=node_id,
                            target=import_record.target_node_id,
                        )

            nodes_by_id[node_id].metadata["import_count"] = len(import_records)
            file_details[node_id] = FileDetail(
                node_id=node_id,
                path=str(relative_path),
                module=module_name,
                imports=import_records,
                classes=classes,
                functions=functions,
                code_blocks=code_blocks,
                code_block_calls=code_block_calls,
                symbol_usages=[],
                source_preview=self._summarize_source(source),
                syntax_error=syntax_error,
            )

        self._apply_cross_file_code_block_calls(file_details, call_contexts)
        self._apply_symbol_usages(file_details, call_contexts)
        self._apply_agent_task_fit_to_file_details(file_details)
        self._classify_leaf_files(nodes_by_id, edges_by_key)
        parse_duration_ms = int((time.perf_counter() - started_at) * 1000)
        nodes = sorted(nodes_by_id.values(), key=lambda node: (node.kind.value, node.label.lower()))
        edges = sorted(edges_by_key.values(), key=lambda edge: (edge.source, edge.target))
        summary = ProjectSummary(
            name=root_path.name,
            root_path=root_path,
            python_files=len(python_files),
            external_packages=sum(1 for node in nodes if node.kind is NodeKind.EXTERNAL_PACKAGE),
            parse_duration_ms=parse_duration_ms,
            parse_errors=parse_errors,
        )
        return ProjectGraph(project=summary, nodes=nodes, edges=edges, file_details=file_details)

    def _discover_python_files(self, root_path: Path) -> list[Path]:
        python_files: list[Path] = []
        for current_root, dirs, files in os.walk(root_path):
            dirs[:] = [directory for directory in dirs if not self._should_ignore_dir(directory)]
            for file_name in files:
                if file_name.endswith(".py"):
                    python_files.append(Path(current_root) / file_name)
        return sorted(python_files)

    def _should_ignore_dir(self, directory_name: str) -> bool:
        return directory_name in IGNORE_DIRS or directory_name.startswith(".")

    def _load_source(self, file_path: Path) -> str:
        return file_path.read_text(encoding="utf-8", errors="replace")

    def _discover_source_roots(self, root_path: Path) -> tuple[Path, ...]:
        source_roots = [root_path]
        for directory_name in SOURCE_ROOT_DIRS:
            candidate = root_path / directory_name
            if candidate.is_dir():
                source_roots.append(candidate)
        return tuple(source_roots)

    def _module_name_for_path(
        self,
        root_path: Path,
        file_path: Path,
        source_roots: tuple[Path, ...] | None = None,
    ) -> str:
        module_root = self._module_root_for_file(root_path, file_path, source_roots)
        relative_path = file_path.relative_to(module_root).with_suffix("")
        parts = list(relative_path.parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else module_root.name

    def _module_root_for_file(
        self,
        root_path: Path,
        file_path: Path,
        source_roots: tuple[Path, ...] | None = None,
    ) -> Path:
        candidates = source_roots or (root_path,)
        matching_roots = [candidate for candidate in candidates if file_path.is_relative_to(candidate)]
        if not matching_roots:
            return root_path
        return max(matching_roots, key=lambda candidate: len(candidate.parts))

    def _file_node_id(self, relative_path: Path) -> str:
        return f"file:{relative_path.as_posix()}"

    def _external_node_id(self, package_name: str) -> str:
        return f"external:{package_name.replace('-', '_').lower()}"

    def _analyze_imports(
        self,
        *,
        root_path: Path,
        file_path: Path,
        module_name: str,
        parsed_tree: ast.Module,
        module_index: dict[str, Path],
    ) -> list[ImportRecord]:
        records: list[ImportRecord] = []
        for node in ast.walk(parsed_tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_module = alias.name
                    target_path = self._resolve_internal_target_path(
                        module_name=imported_module,
                        root_path=root_path,
                        file_path=file_path,
                        module_index=module_index,
                    )
                    if target_path is not None:
                        records.append(
                            ImportRecord(
                                module=imported_module,
                                line=node.lineno,
                                kind=ImportKind.INTERNAL,
                                target_node_id=self._file_node_id(target_path.relative_to(root_path)),
                            )
                        )
                    elif self._is_standard_library(imported_module):
                        records.append(
                            ImportRecord(
                                module=imported_module,
                                line=node.lineno,
                                kind=ImportKind.STANDARD_LIBRARY,
                            )
                        )
                    else:
                        records.append(self._non_internal_import_record(imported_module, node.lineno))

            if isinstance(node, ast.ImportFrom):
                base_module = self._resolve_relative_base(
                    module_name=node.module,
                    current_module=module_name,
                    file_path=file_path,
                    level=node.level,
                )

                for alias in node.names:
                    candidates: list[str] = []
                    if alias.name != "*" and base_module:
                        candidates.append(f"{base_module}.{alias.name}")
                    if base_module:
                        candidates.append(base_module)
                    if alias.name != "*" and not base_module:
                        candidates.append(alias.name)

                    target_path = next(
                        (
                            resolved_path
                            for candidate in candidates
                            if (
                                resolved_path := self._resolve_internal_target_path(
                                    module_name=candidate,
                                    root_path=root_path,
                                    file_path=file_path,
                                    module_index=module_index,
                                )
                            )
                            is not None
                        ),
                        None,
                    )
                    if target_path is not None:
                        display_module = candidates[0] if candidates else base_module or alias.name
                        records.append(
                            ImportRecord(
                                module=display_module,
                                line=node.lineno,
                                kind=ImportKind.INTERNAL,
                                target_node_id=self._file_node_id(target_path.relative_to(root_path)),
                            )
                        )
                    elif base_module and self._is_standard_library(base_module):
                        display_module = base_module if alias.name == "*" else f"{base_module}.{alias.name}"
                        records.append(
                            ImportRecord(
                                module=display_module,
                                line=node.lineno,
                                kind=ImportKind.STANDARD_LIBRARY,
                            )
                        )
                    elif base_module:
                        display_module = base_module if alias.name == "*" else f"{base_module}.{alias.name}"
                        records.append(self._non_internal_import_record(display_module, node.lineno))
                    else:
                        records.append(
                            ImportRecord(
                                module=alias.name,
                                line=node.lineno,
                                kind=ImportKind.UNRESOLVED,
                            )
                        )

        records.sort(key=lambda record: (record.line, record.module))
        return records

    def _current_package_parts(self, current_module: str, file_path: Path) -> list[str]:
        if not current_module:
            return []
        parts = current_module.split(".")
        if file_path.name == "__init__.py":
            return parts
        return parts[:-1]

    def _resolve_relative_base(
        self, *, module_name: str | None, current_module: str, file_path: Path, level: int
    ) -> str:
        if level == 0:
            return module_name or ""
        package_parts = self._current_package_parts(current_module, file_path)
        keep = max(len(package_parts) - max(level - 1, 0), 0)
        base_parts = package_parts[:keep]
        if module_name:
            return ".".join(base_parts + module_name.split("."))
        return ".".join(base_parts)

    def _deepest_internal_candidate(self, module_name: str, module_index: dict[str, Path]) -> str | None:
        candidate = module_name
        while candidate:
            if candidate in module_index:
                return candidate
            if "." not in candidate:
                return None
            candidate = candidate.rsplit(".", 1)[0]
        return None

    def _resolve_internal_target_path(
        self,
        *,
        module_name: str,
        root_path: Path,
        file_path: Path,
        module_index: dict[str, Path],
    ) -> Path | None:
        resolved_module = self._deepest_internal_candidate(module_name, module_index)
        if resolved_module is not None:
            return module_index[resolved_module]
        return self._deepest_nearby_internal_path(module_name, root_path=root_path, file_path=file_path)

    def _deepest_nearby_internal_path(self, module_name: str, *, root_path: Path, file_path: Path) -> Path | None:
        candidate = module_name
        while candidate:
            resolved_path = self._nearby_internal_path(candidate, root_path=root_path, file_path=file_path)
            if resolved_path is not None:
                return resolved_path
            if "." not in candidate:
                return None
            candidate = candidate.rsplit(".", 1)[0]
        return None

    def _nearby_internal_path(self, module_name: str, *, root_path: Path, file_path: Path) -> Path | None:
        parts = [part for part in module_name.split(".") if part]
        if not parts:
            return None

        current = file_path.parent
        while True:
            direct_module = current.joinpath(*parts).with_suffix(".py")
            if direct_module.is_file():
                return direct_module

            package_module = current.joinpath(*parts, "__init__.py")
            if package_module.is_file():
                return package_module

            if current == root_path:
                return None
            current = current.parent

    def _non_internal_import_record(self, module_name: str, line: int) -> ImportRecord:
        package_name = module_name.split(".", 1)[0]
        if self._looks_like_unresolved_internal_name(package_name) and not self._is_installed_module(package_name):
            return ImportRecord(
                module=module_name,
                line=line,
                kind=ImportKind.UNRESOLVED,
            )
        return ImportRecord(
            module=module_name,
            line=line,
            kind=ImportKind.EXTERNAL,
            target_node_id=self._external_node_id(package_name),
        )

    def _looks_like_unresolved_internal_name(self, module_name: str) -> bool:
        return module_name != module_name.lower()

    def _is_installed_module(self, module_name: str) -> bool:
        normalized_name = module_name.replace("-", "_")
        if normalized_name not in self._installed_module_cache:
            self._installed_module_cache[normalized_name] = importlib.util.find_spec(normalized_name) is not None
        return self._installed_module_cache[normalized_name]

    def _classify_leaf_files(
        self,
        nodes_by_id: dict[str, GraphNode],
        edges_by_key: dict[tuple[str, str], GraphEdge],
    ) -> None:
        incoming_internal: dict[str, int] = {}
        outgoing_internal: dict[str, int] = {}

        for node in nodes_by_id.values():
            if node.kind is NodeKind.EXTERNAL_PACKAGE:
                continue
            incoming_internal[node.id] = 0
            outgoing_internal[node.id] = 0

        for edge in edges_by_key.values():
            source_node = nodes_by_id.get(edge.source)
            target_node = nodes_by_id.get(edge.target)
            if source_node is None or target_node is None:
                continue
            if source_node.kind is NodeKind.EXTERNAL_PACKAGE or target_node.kind is NodeKind.EXTERNAL_PACKAGE:
                continue
            outgoing_internal[edge.source] += 1
            incoming_internal[edge.target] += 1

        for node in nodes_by_id.values():
            if node.kind is NodeKind.EXTERNAL_PACKAGE:
                continue
            if node.path and Path(node.path).name == "__init__.py":
                continue
            if outgoing_internal[node.id] == 0 and incoming_internal[node.id] > 0:
                node.kind = NodeKind.LEAF_FILE
            elif incoming_internal[node.id] == 0 and outgoing_internal[node.id] > 0:
                node.kind = NodeKind.TOP_LEVEL_SCRIPT

    def _is_standard_library(self, module_name: str) -> bool:
        top_level = module_name.split(".", 1)[0].replace("-", "_").lower()
        return top_level in STANDARD_LIBRARY_MODULES

    def _extract_classes(self, parsed_tree: ast.Module) -> list[ClassSummary]:
        return [
            ClassSummary(name=node.name, line=node.lineno)
            for node in parsed_tree.body
            if isinstance(node, ast.ClassDef)
        ]

    def _extract_functions(self, parsed_tree: ast.Module) -> list[FunctionSummary]:
        return [
            FunctionSummary(name=node.name, line=node.lineno)
            for node in parsed_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

    def _extract_code_blocks(
        self,
        parsed_tree: ast.Module,
        *,
        node_id: str,
    ) -> tuple[
        list[CodeBlockSummary],
        list[CodeBlockCall],
        list[_RawCodeBlockCall],
        list[_RawInstanceBinding],
        list[_RawSymbolUsage],
    ]:
        extractor = _CodeBlockExtractor(node_id=node_id)
        extractor.visit(parsed_tree)
        return extractor.finalize()

    def _collect_import_bindings(
        self,
        *,
        parsed_tree: ast.Module,
        module_name: str,
        file_path: Path,
        module_index: dict[str, Path],
    ) -> tuple[dict[str, str], dict[str, tuple[str, str]], tuple[str, ...]]:
        module_aliases: dict[str, str] = {}
        symbol_aliases: dict[str, tuple[str, str]] = {}
        star_import_modules: list[str] = []

        for statement in parsed_tree.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    local_name = alias.asname or alias.name.split(".", 1)[0]
                    module_aliases[local_name] = alias.name if alias.asname else alias.name.split(".", 1)[0]
                continue

            if not isinstance(statement, ast.ImportFrom):
                continue

            base_module = self._resolve_relative_base(
                module_name=statement.module,
                current_module=module_name,
                file_path=file_path,
                level=statement.level,
            )
            if not base_module:
                continue

            internal_base = self._deepest_internal_candidate(base_module, module_index)
            if internal_base is None:
                continue

            for alias in statement.names:
                if alias.name == "*":
                    if internal_base not in star_import_modules:
                        star_import_modules.append(internal_base)
                    continue
                local_name = alias.asname or alias.name
                module_candidate = f"{base_module}.{alias.name}"
                if module_candidate in module_index:
                    module_aliases[local_name] = module_candidate
                    continue
                symbol_aliases[local_name] = (base_module, alias.name)

        return module_aliases, symbol_aliases, tuple(star_import_modules)

    def _collect_scoped_symbol_aliases(
        self,
        *,
        raw_symbol_usages: list[_RawSymbolUsage],
        module_name: str,
        file_path: Path,
        module_index: dict[str, Path],
    ) -> dict[str | None, dict[str, tuple[str, str]]]:
        scoped_symbol_aliases: dict[str | None, dict[str, tuple[str, str]]] = {}
        for raw_usage in raw_symbol_usages:
            if raw_usage.import_name is None:
                continue
            local_name = raw_usage.symbol_name or raw_usage.import_name
            if not local_name:
                continue
            base_module = self._resolve_relative_base(
                module_name=raw_usage.import_module,
                current_module=module_name,
                file_path=file_path,
                level=raw_usage.import_level,
            )
            if not base_module:
                continue
            internal_base = self._deepest_internal_candidate(base_module, module_index)
            if internal_base is None:
                continue
            scoped_symbol_aliases.setdefault(raw_usage.owner_block_id, {})[local_name] = (
                base_module,
                raw_usage.import_name,
            )
        return scoped_symbol_aliases

    def _apply_cross_file_code_block_calls(
        self,
        file_details: dict[str, FileDetail],
        call_contexts: dict[str, _ProjectCallContext],
    ) -> None:
        if not call_contexts:
            return

        module_top_level_symbols: dict[str, dict[str, str]] = {}
        module_class_ids: dict[str, dict[str, str]] = {}
        methods_by_class_id: dict[str, dict[str, str]] = {}

        for detail in file_details.values():
            top_level_symbols: dict[str, str] = {}
            class_ids: dict[str, str] = {}
            blocks_by_id = {block.id: block for block in detail.code_blocks}
            for block in detail.code_blocks:
                if block.parent_id is None and block.kind is not CodeBlockKind.MODULE_SCOPE:
                    top_level_symbols[block.name] = block.id
                    if block.kind is CodeBlockKind.CLASS:
                        class_ids[block.name] = block.id
                elif block.parent_id in blocks_by_id and blocks_by_id[block.parent_id].kind is CodeBlockKind.CLASS:
                    methods_by_class_id.setdefault(blocks_by_id[block.parent_id].id, {})[block.name] = block.id
            module_top_level_symbols[detail.module] = top_level_symbols
            module_class_ids[detail.module] = class_ids

        for node_id, context in call_contexts.items():
            detail = file_details.get(node_id)
            if detail is None:
                continue

            existing_keys = {
                (call.source_id, call.line, call.expression, call.target_id)
                for call in detail.code_block_calls
            }
            resolved_raw_keys = {
                (call.source_id, call.line, call.expression)
                for call in detail.code_block_calls
                if not call.is_cross_file
            }
            bindings_by_block: dict[str | None, list[_RawInstanceBinding]] = {}
            for binding in context.raw_instance_bindings:
                bindings_by_block.setdefault(binding.block_id, []).append(binding)
            for block_id in bindings_by_block:
                bindings_by_block[block_id].sort(key=lambda binding: binding.line)

            for raw_call in context.raw_calls:
                if raw_call.source_id is None:
                    continue
                if (raw_call.source_id, raw_call.line, raw_call.expression) in resolved_raw_keys:
                    continue

                target_id = self._resolve_cross_file_call_target(
                    raw_call=raw_call,
                    context=context,
                    bindings_by_block=bindings_by_block,
                    module_top_level_symbols=module_top_level_symbols,
                    module_class_ids=module_class_ids,
                    methods_by_class_id=methods_by_class_id,
                )
                if target_id is None:
                    continue

                edge_key = (raw_call.source_id, raw_call.line, raw_call.expression, target_id)
                if edge_key in existing_keys:
                    continue
                existing_keys.add(edge_key)
                detail.code_block_calls.append(
                    CodeBlockCall(
                        source_id=raw_call.source_id,
                        source_node_id=node_id,
                        target_id=target_id,
                        target_node_id=target_id.split("#block:", 1)[0],
                        line=raw_call.line,
                        expression=raw_call.expression,
                        is_cross_file=True,
                    )
                )

            detail.code_block_calls.sort(key=lambda call: (call.source_id, call.line, call.target_id))

    def _apply_symbol_usages(
        self,
        file_details: dict[str, FileDetail],
        call_contexts: dict[str, _ProjectCallContext],
    ) -> None:
        if not file_details:
            return

        blocks_by_id: dict[str, CodeBlockSummary] = {}
        module_top_level_symbols: dict[str, dict[str, str]] = {}
        module_class_ids: dict[str, dict[str, str]] = {}
        methods_by_class_id: dict[str, dict[str, str]] = {}
        for detail in file_details.values():
            top_level_symbols: dict[str, str] = {}
            class_ids: dict[str, str] = {}
            detail_blocks_by_id = {block.id: block for block in detail.code_blocks}
            for block in detail.code_blocks:
                blocks_by_id[block.id] = block
                if block.parent_id is None and block.kind is not CodeBlockKind.MODULE_SCOPE:
                    top_level_symbols[block.name] = block.id
                    if block.kind is CodeBlockKind.CLASS:
                        class_ids[block.name] = block.id
                elif block.parent_id in detail_blocks_by_id:
                    parent_block = detail_blocks_by_id[block.parent_id]
                    if parent_block.kind is CodeBlockKind.CLASS and block.kind is CodeBlockKind.METHOD:
                        methods_by_class_id.setdefault(parent_block.id, {})[block.name] = block.id
            module_top_level_symbols[detail.module] = top_level_symbols
            module_class_ids[detail.module] = class_ids

        for detail in file_details.values():
            usages: list[SymbolUsage] = []
            seen_keys: set[tuple[str, str | None, int, UsageKind, str]] = set()

            for call in detail.code_block_calls:
                target_block = blocks_by_id.get(call.target_id)
                if target_block is None:
                    continue
                usage = SymbolUsage(
                    target_id=call.target_id,
                    target_node_id=call.target_node_id,
                    source_node_id=call.source_node_id,
                    owner_block_id=call.source_id,
                    line=call.line,
                    expression=call.expression,
                    usage_kind=self._usage_kind_for_call(target_block),
                    confidence=UsageConfidence.EXACT,
                    is_cross_file=call.is_cross_file,
                )
                usage_key = (
                    usage.target_id,
                    usage.owner_block_id,
                    usage.line,
                    usage.usage_kind,
                    usage.expression,
                )
                if usage_key in seen_keys:
                    continue
                seen_keys.add(usage_key)
                usages.append(usage)

            context = call_contexts.get(detail.node_id)
            if context is None:
                detail.symbol_usages = sorted(
                    usages,
                    key=lambda usage: (usage.target_id, usage.line, usage.usage_kind.value, usage.expression),
                )
                continue

            for raw_usage in context.raw_symbol_usages:
                target_id = self._resolve_symbol_usage_target(
                    raw_usage=raw_usage,
                    context=context,
                    module_top_level_symbols=module_top_level_symbols,
                )
                if target_id is None:
                    continue
                target_node_id = target_id.split("#block:", 1)[0]
                usage = SymbolUsage(
                    target_id=target_id,
                    target_node_id=target_node_id,
                    source_node_id=raw_usage.source_node_id,
                    owner_block_id=raw_usage.owner_block_id,
                    line=raw_usage.line,
                    expression=raw_usage.expression,
                    usage_kind=raw_usage.usage_kind,
                    confidence=UsageConfidence.EXACT,
                    is_cross_file=target_node_id != detail.node_id,
                )
                usage_key = (
                    usage.target_id,
                    usage.owner_block_id,
                    usage.line,
                    usage.usage_kind,
                    usage.expression,
                )
                if usage_key in seen_keys:
                    continue
                seen_keys.add(usage_key)
                usages.append(usage)

            bindings_by_block: dict[str | None, list[_RawInstanceBinding]] = {}
            for binding in context.raw_instance_bindings:
                bindings_by_block.setdefault(binding.block_id, []).append(binding)
            for block_id in bindings_by_block:
                bindings_by_block[block_id].sort(key=lambda binding: binding.line)

            for raw_call in context.raw_calls:
                if raw_call.source_id is not None:
                    continue
                target_id = self._resolve_module_scope_call_target(
                    raw_call=raw_call,
                    context=context,
                    bindings_by_block=bindings_by_block,
                    module_top_level_symbols=module_top_level_symbols,
                    module_class_ids=module_class_ids,
                    methods_by_class_id=methods_by_class_id,
                )
                if target_id is None:
                    continue
                target_node_id = target_id.split("#block:", 1)[0]
                target_block = blocks_by_id.get(target_id)
                if target_block is None:
                    continue
                usage = SymbolUsage(
                    target_id=target_id,
                    target_node_id=target_node_id,
                    source_node_id=raw_call.source_node_id,
                    owner_block_id=None,
                    line=raw_call.line,
                    expression=raw_call.expression,
                    usage_kind=self._usage_kind_for_call(target_block),
                    confidence=UsageConfidence.EXACT,
                    is_cross_file=target_node_id != detail.node_id,
                )
                usage_key = (
                    usage.target_id,
                    usage.owner_block_id,
                    usage.line,
                    usage.usage_kind,
                    usage.expression,
                )
                if usage_key in seen_keys:
                    continue
                seen_keys.add(usage_key)
                usages.append(usage)

            detail.symbol_usages = sorted(
                usages,
                key=lambda usage: (usage.target_id, usage.line, usage.usage_kind.value, usage.expression),
            )

    def _usage_kind_for_call(self, target_block: CodeBlockSummary) -> UsageKind:
        if target_block.kind is CodeBlockKind.CLASS:
            return UsageKind.INSTANTIATION
        if target_block.kind is CodeBlockKind.METHOD:
            return UsageKind.METHOD_CALL
        return UsageKind.CALL

    def _resolve_symbol_usage_target(
        self,
        *,
        raw_usage: _RawSymbolUsage,
        context: _ProjectCallContext,
        module_top_level_symbols: dict[str, dict[str, str]],
    ) -> str | None:
        if raw_usage.import_name is not None:
            base_module = self._resolve_relative_base(
                module_name=raw_usage.import_module,
                current_module=context.module_name,
                file_path=context.file_path,
                level=raw_usage.import_level,
            )
            if not base_module:
                return None
            resolved_module = self._known_internal_module(base_module, module_top_level_symbols)
            if resolved_module is None:
                return None
            return module_top_level_symbols.get(resolved_module, {}).get(raw_usage.import_name)

        if raw_usage.attribute_chain is not None:
            return self._resolve_symbol_usage_attribute_chain(
                chain=list(raw_usage.attribute_chain),
                context=context,
                module_top_level_symbols=module_top_level_symbols,
            )

        if raw_usage.symbol_name is not None:
            binding = context.symbol_aliases.get(raw_usage.symbol_name)
            if binding is None:
                binding = context.scoped_symbol_aliases.get(raw_usage.owner_block_id, {}).get(raw_usage.symbol_name)
            if binding is not None:
                target_module, target_symbol = binding
                return module_top_level_symbols.get(target_module, {}).get(target_symbol)
            local_target = module_top_level_symbols.get(context.module_name, {}).get(raw_usage.symbol_name)
            if local_target is not None:
                return local_target
            return self._resolve_star_imported_name_target(
                local_name=raw_usage.symbol_name,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
            )

        return None

    def _resolve_symbol_usage_attribute_chain(
        self,
        *,
        chain: list[str],
        context: _ProjectCallContext,
        module_top_level_symbols: dict[str, dict[str, str]],
    ) -> str | None:
        if len(chain) < 2:
            return None

        root_name = chain[0]
        if root_name in context.module_aliases:
            base_module = context.module_aliases[root_name]
            module_name = base_module if len(chain) == 2 else ".".join([base_module, *chain[1:-1]])
            return module_top_level_symbols.get(module_name, {}).get(chain[-1])

        binding = context.symbol_aliases.get(root_name)
        if binding is not None:
            target_module, target_symbol = binding
            if len(chain) == 1:
                return module_top_level_symbols.get(target_module, {}).get(target_symbol)
            return None
        if len(chain) == 1:
            return self._resolve_star_imported_name_target(
                local_name=root_name,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
            )
        return None

    def _known_internal_module(
        self,
        module_name: str,
        module_top_level_symbols: dict[str, dict[str, str]],
    ) -> str | None:
        candidate = module_name
        while candidate:
            if candidate in module_top_level_symbols:
                return candidate
            if "." not in candidate:
                return None
            candidate = candidate.rsplit(".", 1)[0]
        return None

    def _resolve_cross_file_call_target(
        self,
        *,
        raw_call: _RawCodeBlockCall,
        context: _ProjectCallContext,
        bindings_by_block: dict[str | None, list[_RawInstanceBinding]],
        module_top_level_symbols: dict[str, dict[str, str]],
        module_class_ids: dict[str, dict[str, str]],
        methods_by_class_id: dict[str, dict[str, str]],
    ) -> str | None:
        func_node = raw_call.func_node

        if isinstance(func_node, ast.Name):
            imported_target = self._resolve_imported_name_target(
                local_name=func_node.id,
                owner_block_id=raw_call.source_id,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
            )
            if imported_target is not None:
                return imported_target
            return None

        if isinstance(func_node, ast.Attribute):
            chain = self._attribute_chain(func_node)
            if chain and len(chain) >= 2:
                direct_target = self._resolve_attribute_chain_target(
                    chain=chain,
                    context=context,
                    module_top_level_symbols=module_top_level_symbols,
                    module_class_ids=module_class_ids,
                    methods_by_class_id=methods_by_class_id,
                )
                if direct_target is not None:
                    return direct_target

            if isinstance(func_node.value, ast.Name):
                class_id = self._bound_instance_class_target(
                    block_id=raw_call.source_id,
                    variable_name=func_node.value.id,
                    call_line=raw_call.line,
                    bindings_by_block=bindings_by_block,
                    context=context,
                    module_top_level_symbols=module_top_level_symbols,
                    module_class_ids=module_class_ids,
                )
                if class_id is not None:
                    return methods_by_class_id.get(class_id, {}).get(func_node.attr)

            if isinstance(func_node.value, ast.Call):
                class_id = self._resolve_constructor_call_target(
                    constructor_func=func_node.value.func,
                    owner_block_id=raw_call.source_id,
                    context=context,
                    module_top_level_symbols=module_top_level_symbols,
                    module_class_ids=module_class_ids,
                )
                if class_id is not None:
                    return methods_by_class_id.get(class_id, {}).get(func_node.attr)

        return None

    def _resolve_module_scope_call_target(
        self,
        *,
        raw_call: _RawCodeBlockCall,
        context: _ProjectCallContext,
        bindings_by_block: dict[str | None, list[_RawInstanceBinding]],
        module_top_level_symbols: dict[str, dict[str, str]],
        module_class_ids: dict[str, dict[str, str]],
        methods_by_class_id: dict[str, dict[str, str]],
    ) -> str | None:
        func_node = raw_call.func_node

        if isinstance(func_node, ast.Name):
            local_target = module_top_level_symbols.get(context.module_name, {}).get(func_node.id)
            if local_target is not None:
                return local_target
            return self._resolve_imported_name_target(
                local_name=func_node.id,
                owner_block_id=None,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
            )

        if not isinstance(func_node, ast.Attribute):
            return None

        chain = self._attribute_chain(func_node)
        if chain and len(chain) >= 2:
            direct_target = self._resolve_attribute_chain_target(
                chain=chain,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
                module_class_ids=module_class_ids,
                methods_by_class_id=methods_by_class_id,
            )
            if direct_target is not None:
                return direct_target

        if isinstance(func_node.value, ast.Name):
            class_id = self._bound_instance_class_target(
                block_id=None,
                variable_name=func_node.value.id,
                call_line=raw_call.line,
                bindings_by_block=bindings_by_block,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
                module_class_ids=module_class_ids,
            )
            if class_id is not None:
                return methods_by_class_id.get(class_id, {}).get(func_node.attr)

        if isinstance(func_node.value, ast.Call):
            class_id = self._resolve_constructor_call_target(
                constructor_func=func_node.value.func,
                owner_block_id=None,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
                module_class_ids=module_class_ids,
            )
            if class_id is not None:
                return methods_by_class_id.get(class_id, {}).get(func_node.attr)

        return None

    def _resolve_imported_name_target(
        self,
        *,
        local_name: str,
        owner_block_id: str | None,
        context: _ProjectCallContext,
        module_top_level_symbols: dict[str, dict[str, str]],
    ) -> str | None:
        binding = context.symbol_aliases.get(local_name)
        if binding is None:
            binding = context.scoped_symbol_aliases.get(owner_block_id, {}).get(local_name)
        if binding is not None:
            target_module, target_symbol = binding
            return module_top_level_symbols.get(target_module, {}).get(target_symbol)
        return self._resolve_star_imported_name_target(
            local_name=local_name,
            context=context,
            module_top_level_symbols=module_top_level_symbols,
        )

    def _resolve_attribute_chain_target(
        self,
        *,
        chain: list[str],
        context: _ProjectCallContext,
        module_top_level_symbols: dict[str, dict[str, str]],
        module_class_ids: dict[str, dict[str, str]],
        methods_by_class_id: dict[str, dict[str, str]],
    ) -> str | None:
        root_name = chain[0]

        if root_name in context.module_aliases:
            base_module = context.module_aliases[root_name]
            module_name = base_module
            if len(chain) > 2:
                module_name = ".".join([base_module, *chain[1:-1]])
            return module_top_level_symbols.get(module_name, {}).get(chain[-1])

        symbol_binding = context.symbol_aliases.get(root_name)
        if symbol_binding is not None:
            target_module, target_symbol = symbol_binding
            class_id = module_class_ids.get(target_module, {}).get(target_symbol)
        else:
            class_id = self._resolve_star_imported_class_id(
                local_name=root_name,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
                module_class_ids=module_class_ids,
            )
        if class_id is None:
            return None
        if len(chain) == 2:
            return methods_by_class_id.get(class_id, {}).get(chain[1])
        return None

    def _resolve_constructor_call_target(
        self,
        *,
        constructor_func: ast.AST,
        owner_block_id: str | None,
        context: _ProjectCallContext,
        module_top_level_symbols: dict[str, dict[str, str]],
        module_class_ids: dict[str, dict[str, str]],
    ) -> str | None:
        if isinstance(constructor_func, ast.Name):
            binding = context.symbol_aliases.get(constructor_func.id)
            if binding is None:
                binding = context.scoped_symbol_aliases.get(owner_block_id, {}).get(constructor_func.id)
            if binding is not None:
                target_module, target_symbol = binding
                return module_class_ids.get(target_module, {}).get(target_symbol)
            return self._resolve_star_imported_class_id(
                local_name=constructor_func.id,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
                module_class_ids=module_class_ids,
            )

        chain = self._attribute_chain(constructor_func)
        if not chain:
            return None
        root_name = chain[0]
        if root_name not in context.module_aliases:
            return None
        base_module = context.module_aliases[root_name]
        module_name = base_module
        if len(chain) > 2:
            module_name = ".".join([base_module, *chain[1:-1]])
        return module_class_ids.get(module_name, {}).get(chain[-1])

    def _resolve_star_imported_name_target(
        self,
        *,
        local_name: str,
        context: _ProjectCallContext,
        module_top_level_symbols: dict[str, dict[str, str]],
    ) -> str | None:
        matches = {
            module_top_level_symbols.get(module_name, {}).get(local_name)
            for module_name in context.star_import_modules
        }
        matches.discard(None)
        if len(matches) != 1:
            return None
        return next(iter(matches))

    def _resolve_star_imported_class_id(
        self,
        *,
        local_name: str,
        context: _ProjectCallContext,
        module_top_level_symbols: dict[str, dict[str, str]],
        module_class_ids: dict[str, dict[str, str]],
    ) -> str | None:
        target_id = self._resolve_star_imported_name_target(
            local_name=local_name,
            context=context,
            module_top_level_symbols=module_top_level_symbols,
        )
        if target_id is None:
            return None
        for class_ids in module_class_ids.values():
            if class_ids.get(local_name) == target_id:
                return target_id
        return None

    def _bound_instance_class_target(
        self,
        *,
        block_id: str | None,
        variable_name: str,
        call_line: int,
        bindings_by_block: dict[str | None, list[_RawInstanceBinding]],
        context: _ProjectCallContext,
        module_top_level_symbols: dict[str, dict[str, str]],
        module_class_ids: dict[str, dict[str, str]],
    ) -> str | None:
        latest_target: str | None = None
        for binding in bindings_by_block.get(block_id, []):
            if binding.variable_name != variable_name or binding.line > call_line:
                continue
            latest_target = self._resolve_constructor_call_target(
                constructor_func=binding.constructor_node,
                owner_block_id=block_id,
                context=context,
                module_top_level_symbols=module_top_level_symbols,
                module_class_ids=module_class_ids,
            )
        return latest_target

    def _attribute_chain(self, node: ast.AST) -> list[str] | None:
        parts: list[str] = []
        current: ast.AST | None = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        parts.append(current.id)
        parts.reverse()
        return parts

    def _apply_agent_task_fit_to_file_details(self, file_details: dict[str, FileDetail]) -> None:
        all_calls = [call for detail in file_details.values() for call in detail.code_block_calls]
        incoming: dict[str, list[CodeBlockCall]] = {}
        outgoing: dict[str, list[CodeBlockCall]] = {}

        for call in all_calls:
            outgoing.setdefault(call.source_id, []).append(call)
            incoming.setdefault(call.target_id, []).append(call)

        for detail in file_details.values():
            blocks_by_id = {block.id: block for block in detail.code_blocks}
            children_by_parent: dict[str, list[CodeBlockSummary]] = {}
            for block in detail.code_blocks:
                outgoing.setdefault(block.id, [])
                incoming.setdefault(block.id, [])
                if block.parent_id is not None and block.parent_id in blocks_by_id:
                    children_by_parent.setdefault(block.parent_id, []).append(block)

            for block in detail.code_blocks:
                line_span = max(block.end_line - block.line + 1, 1)
                child_count = len(children_by_parent.get(block.id, []))
                outgoing_count = len(outgoing.get(block.id, []))
                incoming_count = len(incoming.get(block.id, []))
                fit, reasons = self._task_fit_for_block(
                    block=block,
                    line_span=line_span,
                    child_count=child_count,
                    outgoing_count=outgoing_count,
                    incoming_count=incoming_count,
                    blocks_by_id=blocks_by_id,
                )
                block.agent_task_fit = fit
                block.agent_task_reasons = reasons

    def _task_fit_for_block(
        self,
        *,
        block: CodeBlockSummary,
        line_span: int,
        child_count: int,
        outgoing_count: int,
        incoming_count: int,
        blocks_by_id: dict[str, CodeBlockSummary],
    ) -> tuple[AgentTaskSuitability, list[str]]:
        reasons: list[str] = []

        if block.kind is CodeBlockKind.MODULE_SCOPE:
            reasons.append("module-scope execution usually needs file-level context")
            if line_span > 80 or outgoing_count > 4 or child_count > 0:
                reasons.append("module-scope block is large or fans out too widely")
                return AgentTaskSuitability.AVOID, reasons
            if incoming_count:
                reasons.append(f"referenced by {incoming_count} block(s)")
            reasons.append("script-style work can be handled, but keep surrounding setup visible")
            return AgentTaskSuitability.CAUTION, reasons

        if block.kind is CodeBlockKind.CLASS:
            reasons.append(f"{child_count} direct child blocks")
            if line_span > 140 or child_count > 6:
                reasons.append("class is large enough that it should be split before agent work")
                return AgentTaskSuitability.AVOID, reasons
            reasons.append("class work usually needs shared state and method context")
            return AgentTaskSuitability.CAUTION, reasons

        if block.parent_id and block.parent_id in blocks_by_id and blocks_by_id[block.parent_id].kind is CodeBlockKind.CLASS:
            if block.name.startswith("__") and block.name.endswith("__"):
                reasons.append("dunder methods are tightly coupled to class behavior")
                return AgentTaskSuitability.AVOID, reasons
            if block.name.startswith("_"):
                reasons.append("private methods are usually implementation details of the class")
            else:
                reasons.append("method changes still need surrounding class context")
            if line_span > 50 or outgoing_count > 2:
                reasons.append("method has enough local coupling that a wider task is safer")
                return AgentTaskSuitability.AVOID, reasons
            reasons.append("small method can be handed off with class context attached")
            return AgentTaskSuitability.CAUTION, reasons

        if block.depth > 0:
            reasons.append("nested blocks depend on enclosing scope")
            if line_span > 40 or outgoing_count > 1:
                reasons.append("nested block is not isolated enough for a standalone task")
                return AgentTaskSuitability.AVOID, reasons
            return AgentTaskSuitability.CAUTION, reasons

        if line_span <= 35 and outgoing_count <= 2 and child_count == 0:
            reasons.append("small top-level block with limited block-level coupling")
            if incoming_count:
                reasons.append(f"called by {incoming_count} block(s)")
            return AgentTaskSuitability.GOOD, reasons

        if line_span > 100 or outgoing_count > 4 or child_count > 1:
            reasons.append("block is large or fans out to many sibling blocks")
            return AgentTaskSuitability.AVOID, reasons

        reasons.append("top-level block is workable but still needs nearby context")
        if outgoing_count:
            reasons.append(f"depends on {outgoing_count} block(s)")
        return AgentTaskSuitability.CAUTION, reasons

    def _summarize_source(self, source: str) -> str:
        preview = "\n".join(source.splitlines()[:SOURCE_PREVIEW_MAX_LINES])
        if len(preview) > SOURCE_PREVIEW_MAX_CHARS:
            preview = preview[:SOURCE_PREVIEW_MAX_CHARS]
        return preview
