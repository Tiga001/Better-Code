from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from bettercode.models import AgentTaskSuitability, TaskMode, TaskUnitKind
from bettercode.parser import ProjectAnalyzer
from bettercode.task_graph import (
    build_task_execution_plan,
    build_task_graph,
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


if __name__ == "__main__":
    unittest.main()
