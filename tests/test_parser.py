from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from bettercode.models import AgentTaskSuitability, CodeBlockKind, ImportKind, NodeKind, UsageKind
from bettercode.parser import ProjectAnalyzer


class ProjectAnalyzerTests(unittest.TestCase):
    def test_builds_file_level_dependency_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "pkg").mkdir()
            (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (root / "pkg" / "helpers.py").write_text(
                "import os\n\n\ndef normalize(value: str) -> str:\n    return value.strip() + os.sep\n",
                encoding="utf-8",
            )
            (root / "lonely.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "main.py").write_text(
                textwrap.dedent(
                    """
                    import pkg
                    import requests
                    import os
                    from pkg.helpers import normalize

                    def run() -> str:
                        return normalize(" ok ")

                    if __name__ == "__main__":
                        print(run())
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        node_kinds = {node.id: node.kind for node in graph.nodes}
        self.assertEqual(node_kinds["file:main.py"], NodeKind.TOP_LEVEL_SCRIPT)
        self.assertEqual(node_kinds["file:pkg/__init__.py"], NodeKind.PYTHON_FILE)
        self.assertEqual(node_kinds["file:pkg/helpers.py"], NodeKind.LEAF_FILE)
        self.assertEqual(node_kinds["file:lonely.py"], NodeKind.PYTHON_FILE)
        self.assertEqual(node_kinds["external:requests"], NodeKind.EXTERNAL_PACKAGE)

        edges = {(edge.source, edge.target) for edge in graph.edges}
        self.assertIn(("file:main.py", "file:pkg/__init__.py"), edges)
        self.assertIn(("file:main.py", "file:pkg/helpers.py"), edges)
        self.assertIn(("file:main.py", "external:requests"), edges)

        detail = graph.file_details["file:main.py"]
        import_kinds = {record.module: record.kind for record in detail.imports}
        self.assertEqual(import_kinds["pkg"], ImportKind.INTERNAL)
        self.assertEqual(import_kinds["requests"], ImportKind.EXTERNAL)
        self.assertEqual(import_kinds["os"], ImportKind.STANDARD_LIBRARY)
        self.assertEqual(import_kinds["pkg.helpers.normalize"], ImportKind.INTERNAL)
        self.assertEqual(graph.project.python_files, 4)

    def test_absolute_from_imports_stay_absolute_inside_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_sample.py").write_text(
                textwrap.dedent(
                    """
                    from pathlib import Path
                    from core import VALUE
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:tests/test_sample.py"]
        import_kinds = {record.module: record.kind for record in detail.imports}
        self.assertEqual(import_kinds["pathlib.Path"], ImportKind.STANDARD_LIBRARY)
        self.assertEqual(import_kinds["core.VALUE"], ImportKind.INTERNAL)
        self.assertNotIn("external:tests", {node.id for node in graph.nodes})

    def test_src_layout_modules_are_not_treated_as_external_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "src" / "myapp").mkdir(parents=True)
            (root / "src" / "myapp" / "__init__.py").write_text("", encoding="utf-8")
            (root / "src" / "myapp" / "helpers.py").write_text(
                textwrap.dedent(
                    """
                    def normalize(value: str) -> str:
                        return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "src" / "myapp" / "service.py").write_text(
                textwrap.dedent(
                    """
                    import myapp.helpers
                    from myapp.helpers import normalize

                    def run(value: str) -> str:
                        return normalize(value)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        self.assertNotIn("external:myapp", {node.id for node in graph.nodes})
        self.assertEqual(graph.file_details["file:src/myapp/service.py"].module, "myapp.service")
        import_kinds = {record.module: record.kind for record in graph.file_details["file:src/myapp/service.py"].imports}
        self.assertEqual(import_kinds["myapp.helpers"], ImportKind.INTERNAL)
        self.assertEqual(import_kinds["myapp.helpers.normalize"], ImportKind.INTERNAL)

    def test_same_directory_bare_import_resolves_to_internal_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "ui").mkdir()
            (root / "ui" / "DICT2MODEL.py").write_text(
                "def Conf2MODEL(config):\n    return config\n",
                encoding="utf-8",
            )
            (root / "ui" / "JSONdemo.py").write_text(
                textwrap.dedent(
                    """
                    from DICT2MODEL import Conf2MODEL
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:ui/JSONdemo.py"]
        import_record = next(record for record in detail.imports if record.module == "DICT2MODEL.Conf2MODEL")
        self.assertEqual(import_record.kind, ImportKind.INTERNAL)
        self.assertEqual(import_record.target_node_id, "file:ui/DICT2MODEL.py")
        self.assertNotIn("external:dict2model", {node.id for node in graph.nodes})

    def test_sibling_package_import_resolves_with_container_directory_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "DemosPyCode" / "Data").mkdir(parents=True)
            (root / "DemosPyCode" / "Data" / "__init__.py").write_text("", encoding="utf-8")
            (root / "DemosPyCode" / "Data" / "DataDemo1.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "DemosPyCode" / "Demo1.py").write_text(
                textwrap.dedent(
                    """
                    from Data.DataDemo1 import VALUE
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:DemosPyCode/Demo1.py"]
        import_record = next(record for record in detail.imports if record.module == "Data.DataDemo1.VALUE")
        self.assertEqual(import_record.kind, ImportKind.INTERNAL)
        self.assertEqual(import_record.target_node_id, "file:DemosPyCode/Data/DataDemo1.py")
        self.assertNotIn("external:data", {node.id for node in graph.nodes})

    def test_uppercase_missing_import_is_unresolved_instead_of_external(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text(
                textwrap.dedent(
                    """
                    from Component import Components
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:main.py"]
        import_record = next(record for record in detail.imports if record.module == "Component.Components")
        self.assertEqual(import_record.kind, ImportKind.UNRESOLVED)
        self.assertNotIn("external:component", {node.id for node in graph.nodes})

    def test_classifies_top_level_scripts_separately_from_dependency_leaves(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "shared.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "entry.py").write_text(
                textwrap.dedent(
                    """
                    from shared import VALUE

                    print(VALUE)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "worker.py").write_text(
                textwrap.dedent(
                    """
                    from shared import VALUE

                    def run() -> int:
                        return VALUE
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        node_kinds = {node.id: node.kind for node in graph.nodes}
        self.assertEqual(node_kinds["file:entry.py"], NodeKind.TOP_LEVEL_SCRIPT)
        self.assertEqual(node_kinds["file:shared.py"], NodeKind.LEAF_FILE)
        self.assertEqual(node_kinds["file:worker.py"], NodeKind.TOP_LEVEL_SCRIPT)

    def test_ignores_generated_validation_workspaces(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "MainClasses.py").write_text(
                "from LogsPage import LogPage\n",
                encoding="utf-8",
            )
            (root / "LogsPage.py").write_text(
                "import redis\nfrom CustomWidgets import Splitter\n",
                encoding="utf-8",
            )
            generated_logs = (
                root
                / "generated"
                / "optimizations"
                / "task_unit_file_CustomWidgets.py_block_6_optimize"
                / "validation_workspace"
                / "LogsPage.py"
            )
            generated_logs.parent.mkdir(parents=True)
            generated_logs.write_text(
                "import redis\nfrom CustomWidgets import Splitter\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        node_ids = {node.id for node in graph.nodes}
        self.assertIn("file:LogsPage.py", node_ids)
        self.assertNotIn(
            "file:generated/optimizations/task_unit_file_CustomWidgets.py_block_6_optimize/validation_workspace/LogsPage.py",
            node_ids,
        )

    def test_extracts_file_internal_code_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    class Greeter:
                        def greet(self, name: str) -> str:
                            return self._normalize(name)

                        def _normalize(self, name: str) -> str:
                            return name.strip()

                    def run(value: str) -> str:
                        return Greeter().greet(value)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:service.py"]
        blocks = detail.code_blocks
        self.assertEqual(
            [(block.kind, block.name) for block in blocks],
            [
                (CodeBlockKind.CLASS, "Greeter"),
                (CodeBlockKind.METHOD, "greet"),
                (CodeBlockKind.METHOD, "_normalize"),
                (CodeBlockKind.FUNCTION, "run"),
            ],
        )
        self.assertIsNone(blocks[0].parent_id)
        self.assertEqual(blocks[1].parent_id, blocks[0].id)
        self.assertEqual(blocks[2].parent_id, blocks[0].id)
        self.assertIsNone(blocks[3].parent_id)
        self.assertEqual(blocks[0].line, 1)
        self.assertGreaterEqual(blocks[0].end_line, blocks[2].end_line)
        self.assertEqual(blocks[1].parameters, ["name: str"])
        self.assertEqual(blocks[1].return_summary, "str")
        self.assertEqual(blocks[3].agent_task_fit, AgentTaskSuitability.GOOD)
        self.assertEqual(blocks[2].agent_task_fit, AgentTaskSuitability.CAUTION)

        call_edges = {
            (
                next(block.name for block in blocks if block.id == call.source_id),
                next(block.name for block in blocks if block.id == call.target_id),
                call.expression,
            )
            for call in detail.code_block_calls
        }
        self.assertIn(("greet", "_normalize", "self._normalize"), call_edges)
        self.assertIn(("run", "Greeter", "Greeter"), call_edges)
        self.assertIn(("run", "greet", "Greeter().greet"), call_edges)

    def test_resolves_inheritance_through_internal_star_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "Basement.py").write_text(
                textwrap.dedent(
                    """
                    class Unit:
                        pass
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "ModelLib.py").write_text(
                textwrap.dedent(
                    """
                    from Basement import *

                    class Heater(Unit):
                        pass
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        model_detail = graph.file_details["file:ModelLib.py"]
        inheritance_usages = [
            usage
            for usage in model_detail.symbol_usages
            if usage.usage_kind is UsageKind.INHERITANCE
        ]
        self.assertEqual(len(inheritance_usages), 1)
        self.assertEqual(inheritance_usages[0].expression, "Unit")
        self.assertEqual(inheritance_usages[0].target_id, "file:Basement.py#block:0")
        self.assertEqual(inheritance_usages[0].target_node_id, "file:Basement.py")

    def test_resolves_cross_file_code_block_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    class Formatter:
                        def normalize(self, value: str) -> str:
                            return value.strip()

                    def format_value(value: str) -> str:
                        return Formatter().normalize(value)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    from helper import Formatter, format_value

                    def run(raw: str) -> str:
                        return format_value(raw)

                    def run_method(raw: str) -> str:
                        formatter = Formatter()
                        return formatter.normalize(raw)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:service.py"]
        blocks_by_id = {block.id: block for block in detail.code_blocks}
        call_edges = {
            (
                blocks_by_id[call.source_id].name,
                call.target_node_id,
                call.target_id,
                call.expression,
                call.is_cross_file,
            )
            for call in detail.code_block_calls
        }
        helper_blocks = {block.name: block.id for block in graph.file_details["file:helper.py"].code_blocks}
        self.assertIn(
            ("run", "file:helper.py", helper_blocks["format_value"], "format_value", True),
            call_edges,
        )
        self.assertIn(
            ("run_method", "file:helper.py", helper_blocks["Formatter"], "Formatter", True),
            call_edges,
        )
        self.assertIn(
            ("run_method", "file:helper.py", helper_blocks["normalize"], "formatter.normalize", True),
            call_edges,
        )

    def test_collects_symbol_usages_for_imports_and_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    class Formatter:
                        def normalize(self, value: str) -> str:
                            return value.strip()

                    def decorate(fn):
                        return fn
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    from helper import Formatter, decorate

                    class Derived(Formatter):
                        pass

                    @decorate
                    def run(value: Formatter) -> Formatter:
                        formatter = Formatter()
                        return formatter
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        helper_blocks = {block.name: block.id for block in graph.file_details["file:helper.py"].code_blocks}
        service_detail = graph.file_details["file:service.py"]
        usages = {
            (
                usage.target_id,
                usage.owner_block_id,
                usage.line,
                usage.usage_kind,
                usage.expression,
            )
            for usage in service_detail.symbol_usages
        }
        run_block = next(block for block in service_detail.code_blocks if block.name == "run")
        derived_block = next(block for block in service_detail.code_blocks if block.name == "Derived")

        self.assertIn(
            (helper_blocks["Formatter"], None, 1, UsageKind.IMPORT, "helper.Formatter"),
            usages,
        )
        self.assertIn(
            (helper_blocks["decorate"], None, 1, UsageKind.IMPORT, "helper.decorate"),
            usages,
        )
        self.assertIn(
            (helper_blocks["Formatter"], derived_block.id, 3, UsageKind.INHERITANCE, "Formatter"),
            usages,
        )
        self.assertIn(
            (helper_blocks["decorate"], run_block.id, 6, UsageKind.DECORATOR, "decorate"),
            usages,
        )
        self.assertIn(
            (helper_blocks["Formatter"], run_block.id, 7, UsageKind.TYPE_ANNOTATION, "Formatter"),
            usages,
        )
        self.assertIn(
            (helper_blocks["Formatter"], run_block.id, 8, UsageKind.INSTANTIATION, "Formatter"),
            usages,
        )

    def test_collects_module_scope_instantiation_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    class Formatter:
                        pass
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    from helper import Formatter

                    formatter = Formatter()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        helper_block = next(block for block in graph.file_details["file:helper.py"].code_blocks if block.name == "Formatter")
        module_scope_block = next(
            block for block in graph.file_details["file:service.py"].code_blocks if block.kind is CodeBlockKind.MODULE_SCOPE
        )
        service_usages = {
            (
                usage.target_id,
                usage.owner_block_id,
                usage.line,
                usage.usage_kind,
                usage.expression,
            )
            for usage in graph.file_details["file:service.py"].symbol_usages
        }
        self.assertIn(
            (helper_block.id, module_scope_block.id, 3, UsageKind.INSTANTIATION, "Formatter"),
            service_usages,
        )

    def test_extracts_module_scope_execution_block_and_cross_file_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    def normalize(value: str) -> str:
                        return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "demo.py").write_text(
                textwrap.dedent(
                    """
                    from helper import normalize

                    VALUE = " ready "
                    result = normalize(VALUE)
                    if result:
                        print(result)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        detail = graph.file_details["file:demo.py"]
        self.assertEqual(len(detail.code_blocks), 1)
        module_scope_block = detail.code_blocks[0]
        self.assertEqual(module_scope_block.kind, CodeBlockKind.MODULE_SCOPE)
        self.assertEqual(module_scope_block.line, 4)
        self.assertEqual(module_scope_block.end_line, 6)
        self.assertEqual(module_scope_block.agent_task_fit, AgentTaskSuitability.CAUTION)

        helper_block = next(block for block in graph.file_details["file:helper.py"].code_blocks if block.name == "normalize")
        self.assertIn(
            (module_scope_block.id, helper_block.id, "normalize", True),
            {
                (call.source_id, call.target_id, call.expression, call.is_cross_file)
                for call in detail.code_block_calls
            },
        )
        self.assertIn(
            (helper_block.id, module_scope_block.id, 4, UsageKind.CALL, "normalize"),
            {
                (usage.target_id, usage.owner_block_id, usage.line, usage.usage_kind, usage.expression)
                for usage in detail.symbol_usages
            },
        )


if __name__ == "__main__":
    unittest.main()
