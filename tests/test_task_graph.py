from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from bettercode.models import AgentTaskSuitability, TaskDependencyKind, TaskMode, TaskUnitKind
from bettercode.parser import ProjectAnalyzer
from bettercode.task_graph import (
    build_task_batch,
    build_task_execution_plan,
    build_task_graph,
    build_task_unit_package,
    task_batch_to_dict,
    task_execution_plan_to_dict,
    task_graph_to_dict,
)


class TaskGraphTests(unittest.TestCase):
    def test_builds_bottom_up_task_graph_for_top_level_functions(self) -> None:
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
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    from helper import normalize

                    def run(value: str) -> str:
                        return normalize(value).upper()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "app.py").write_text(
                textwrap.dedent(
                    """
                    from service import run

                    def main(raw: str) -> str:
                        return run(raw)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        task_graph = build_task_graph(graph)
        units_by_label = {unit.label: unit for unit in task_graph.units}
        normalize_unit = next(unit for unit in task_graph.units if unit.label.startswith("normalize("))
        run_unit = next(unit for unit in task_graph.units if unit.label.startswith("run("))
        main_unit = next(unit for unit in task_graph.units if unit.label.startswith("main("))

        self.assertEqual(normalize_unit.depth, 0)
        self.assertTrue(normalize_unit.ready_to_run)
        self.assertIn(normalize_unit.id, run_unit.depends_on)
        self.assertIn(run_unit.id, main_unit.depends_on)
        self.assertEqual(run_unit.depth, 1)
        self.assertEqual(main_unit.depth, 2)
        self.assertEqual(units_by_label[normalize_unit.label].kind, TaskUnitKind.FUNCTION)

        optimize_plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
        self.assertEqual([item.label for item in optimize_plan.items[:3]], [normalize_unit.label, run_unit.label, main_unit.label])
        self.assertEqual(optimize_plan.items[0].depth, 0)
        self.assertEqual(optimize_plan.items[1].depends_on, [f"{normalize_unit.id}:optimize"])
        self.assertEqual(optimize_plan.items[1].context_depends_on, [])

        serialized = task_graph_to_dict(task_graph)
        self.assertEqual(serialized["units"][0]["kind"], "function")
        json.dumps(serialized, ensure_ascii=False)

    def test_groups_class_methods_into_single_task_unit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "worker.py").write_text(
                textwrap.dedent(
                    """
                    class Worker:
                        def normalize(self, value: str) -> str:
                            return value.strip()

                        def run(self, value: str) -> str:
                            return self.normalize(value)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "app.py").write_text(
                textwrap.dedent(
                    """
                    from worker import Worker

                    def start(raw: str) -> str:
                        worker = Worker()
                        return worker.run(raw)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        task_graph = build_task_graph(graph)
        class_unit = next(unit for unit in task_graph.units if unit.kind is TaskUnitKind.CLASS_GROUP)
        self.assertEqual(class_unit.node_ids, ["file:worker.py"])
        self.assertEqual(len(class_unit.root_block_ids), 1)
        self.assertGreaterEqual(len(class_unit.block_ids), 3)
        self.assertTrue(any("class methods are grouped" in reason for reason in class_unit.reasons))

        translate_plan = build_task_execution_plan(graph, mode=TaskMode.TRANSLATE)
        class_item = next(item for item in translate_plan.items if item.unit_id == class_unit.id)
        self.assertEqual(class_item.suitability, AgentTaskSuitability.AVOID)
        self.assertTrue(any("top-level functions" in reason for reason in class_item.reasons))
        self.assertEqual(class_item.target_block_ids, class_unit.root_block_ids)

        package = build_task_unit_package(graph, unit_id=class_unit.id, mode=TaskMode.OPTIMIZE)
        self.assertEqual([block.id for block in package.target_blocks], class_unit.root_block_ids)

    def test_merges_mutual_calls_into_one_cycle_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "a.py").write_text(
                textwrap.dedent(
                    """
                    from b import second

                    def first(value: str) -> str:
                        return second(value)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "b.py").write_text(
                textwrap.dedent(
                    """
                    from a import first

                    def second(value: str) -> str:
                        if value:
                            return value
                        return first("fallback")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        task_graph = build_task_graph(graph)
        self.assertEqual(len(task_graph.units), 1)
        cycle_unit = task_graph.units[0]
        self.assertEqual(cycle_unit.kind, TaskUnitKind.CYCLE_GROUP)
        self.assertEqual(cycle_unit.depth, 0)
        self.assertTrue(cycle_unit.ready_to_run)
        self.assertEqual(len(cycle_unit.root_block_ids), 2)
        self.assertTrue(any("mutual internal dependencies" in reason for reason in cycle_unit.reasons))

        plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
        self.assertEqual(len(plan.items), 1)
        self.assertEqual(plan.items[0].target_block_ids, cycle_unit.block_ids)
        self.assertEqual(plan.items[0].depends_on, [])
        serialized = task_execution_plan_to_dict(plan)
        self.assertEqual(serialized["mode"], "optimize")
        json.dumps(serialized, ensure_ascii=False)

    def test_builds_script_block_task_unit_for_module_scope_execution(self) -> None:
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

                    result = normalize(" ok ")
                    print(result)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        task_graph = build_task_graph(graph)
        normalize_unit = next(unit for unit in task_graph.units if unit.label.startswith("normalize("))
        script_unit = next(unit for unit in task_graph.units if unit.kind is TaskUnitKind.SCRIPT_BLOCK)

        self.assertEqual(script_unit.depth, 1)
        self.assertEqual(script_unit.depends_on, [normalize_unit.id])
        self.assertFalse(script_unit.ready_to_run)
        self.assertTrue(any("module-scope execution statements" in reason for reason in script_unit.reasons))

        optimize_plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
        self.assertEqual([item.label for item in optimize_plan.items[:2]], [normalize_unit.label, script_unit.label])

        translate_plan = build_task_execution_plan(graph, mode=TaskMode.TRANSLATE)
        script_item = next(item for item in translate_plan.items if item.unit_id == script_unit.id)
        self.assertEqual(script_item.suitability, AgentTaskSuitability.AVOID)
        self.assertTrue(any("module-scope execution blocks" in reason for reason in script_item.reasons))

    def test_import_edges_attach_only_to_units_that_use_the_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    def format_value(value: str) -> str:
                        return value.strip()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "backend.py").write_text(
                textwrap.dedent(
                    """
                    from helper import format_value

                    POOL = object()

                    class Backend:
                        def run(self, value: str) -> str:
                            return format_value(value)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        task_graph = build_task_graph(graph)
        helper_unit = next(unit for unit in task_graph.units if unit.label.startswith("format_value("))
        script_unit = next(unit for unit in task_graph.units if unit.kind is TaskUnitKind.SCRIPT_BLOCK)
        class_unit = next(unit for unit in task_graph.units if unit.kind is TaskUnitKind.CLASS_GROUP)

        self.assertNotIn(helper_unit.id, script_unit.depends_on)
        self.assertIn(helper_unit.id, class_unit.depends_on)
        dependency_edge = next(
            edge
            for edge in task_graph.edges
            if edge.source == class_unit.id and edge.target == helper_unit.id
        )
        self.assertTrue(dependency_edge.is_blocking)
        self.assertIn(TaskDependencyKind.STRONG_CALL, dependency_edge.dependency_kinds)

    def test_star_imported_base_class_creates_task_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "Basement.py").write_text(
                textwrap.dedent(
                    """
                    class Unit:
                        def setup(self) -> None:
                            return None
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
                        def run(self) -> None:
                            return None
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        task_graph = build_task_graph(graph)
        unit_base = next(unit for unit in task_graph.units if unit.label.startswith("class Unit"))
        heater_unit = next(unit for unit in task_graph.units if unit.label.startswith("class Heater(Unit)"))

        self.assertIn(unit_base.id, heater_unit.depends_on)
        self.assertEqual(unit_base.depth, 0)
        self.assertEqual(heater_unit.depth, 1)
        dependency_edge = next(
            edge
            for edge in task_graph.edges
            if edge.source == heater_unit.id and edge.target == unit_base.id
        )
        self.assertTrue(dependency_edge.is_blocking)
        self.assertIn(TaskDependencyKind.INHERITANCE, dependency_edge.dependency_kinds)

    def test_method_local_import_attaches_dependency_to_class_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "helper.py").write_text(
                textwrap.dedent(
                    """
                    def generator() -> str:
                        return "ok"
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "reactions.py").write_text(
                textwrap.dedent(
                    """
                    class Reaction:
                        def deactivate(self):
                            from helper import generator
                            return generator()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        task_graph = build_task_graph(graph)
        helper_unit = next(unit for unit in task_graph.units if unit.label.startswith("generator("))
        class_unit = next(unit for unit in task_graph.units if unit.kind is TaskUnitKind.CLASS_GROUP)
        self.assertIn(helper_unit.id, class_unit.depends_on)

    def test_import_only_dependency_adds_context_but_not_blocking_order(self) -> None:
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
            (root / "app.py").write_text(
                textwrap.dedent(
                    """
                    from helper import normalize

                    def run(value: str) -> str:
                        return value.upper()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        task_graph = build_task_graph(graph)
        helper_unit = next(unit for unit in task_graph.units if unit.label.startswith("normalize("))
        run_unit = next(unit for unit in task_graph.units if unit.label.startswith("run("))

        self.assertNotIn(helper_unit.id, run_unit.depends_on)
        self.assertIn(helper_unit.id, run_unit.context_depends_on)
        self.assertEqual(run_unit.depth, 0)
        self.assertTrue(run_unit.ready_to_run)

        dependency_edge = next(
            edge
            for edge in task_graph.edges
            if edge.source == run_unit.id and edge.target == helper_unit.id
        )
        self.assertFalse(dependency_edge.is_blocking)
        self.assertEqual(dependency_edge.dependency_kinds, [TaskDependencyKind.IMPORT_ONLY])

        plan = build_task_execution_plan(graph, mode=TaskMode.OPTIMIZE)
        run_item = next(item for item in plan.items if item.label.startswith("run("))
        helper_item = next(item for item in plan.items if item.label.startswith("normalize("))
        self.assertEqual(run_item.depends_on, [])
        self.assertEqual(run_item.context_depends_on, [helper_item.id])

    def test_builds_task_batch_phases_from_blocking_depth(self) -> None:
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
            (root / "service.py").write_text(
                textwrap.dedent(
                    """
                    from helper import normalize

                    def run(value: str) -> str:
                        return normalize(value).upper()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            (root / "app.py").write_text(
                textwrap.dedent(
                    """
                    from helper import normalize
                    from service import run

                    def main(raw: str) -> str:
                        return run(raw) + normalize(raw)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            graph = ProjectAnalyzer().analyze(root)

        batch = build_task_batch(graph, mode=TaskMode.OPTIMIZE)
        self.assertEqual([phase.index for phase in batch.phases], [0, 1, 2])
        self.assertEqual(len(batch.phases[0].item_ids), 1)
        self.assertEqual(len(batch.phases[1].item_ids), 1)
        self.assertEqual(len(batch.phases[2].item_ids), 1)

        main_item = next(item for item in batch.items if item.label.startswith("main("))
        run_item = next(item for item in batch.items if item.label.startswith("run("))
        normalize_item = next(item for item in batch.items if item.label.startswith("normalize("))
        self.assertEqual(main_item.phase_index, 2)
        self.assertEqual(run_item.phase_index, 1)
        self.assertEqual(normalize_item.phase_index, 0)
        self.assertIn(run_item.id, main_item.blocking_dependencies)
        self.assertIn(normalize_item.id, main_item.blocking_dependencies)

        serialized = task_batch_to_dict(batch)
        self.assertEqual(serialized["phases"][0]["index"], 0)
        json.dumps(serialized, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
