"""Structural invariants, replay accounting, and reference-adapter regressions."""
import copy
import json
import math
import unittest

from lab.dradd import Workload, accepted, reduce, trial_summary, wilson
from lab.research_targets import FIFOAdapter, RegisterAdapter, fixture


class Fake:
    signature = "target"

    def __init__(self, outcomes=None):
        self.outcomes = outcomes
        self.calls = 0

    def validate(self, workload):
        pass

    def metadata(self):
        return {"target": "test-only"}

    def execute(self, workload, seed):
        self.calls += 1
        if self.outcomes:
            return copy.deepcopy(self.outcomes[(self.calls - 1) % len(self.outcomes)])
        return {"status": "fail" if {"op": "read", "count": 1} in workload["operations"] else "pass",
                "signature": self.signature, "operations_executed": len(workload["operations"])}


class DRADDTests(unittest.TestCase):
    def test_wilson_known_endpoints(self):
        self.assertIsNone(wilson(0, 0))
        self.assertAlmostEqual(wilson(0, 10)[1], 0.2775328, places=6)
        self.assertAlmostEqual(wilson(10, 10)[0], 0.7224672, places=6)
        self.assertAlmostEqual(sum(wilson(5, 10)), 1)
        for k, n in [(-1, 2), (3, 2), (True, 2)]:
            with self.assertRaises(ValueError):
                wilson(k, n)

    def test_trial_accounting_excludes_invalid_from_denominator(self):
        outcomes = [{"status": "fail", "signature": "target"}, {"status": "pass"},
                    {"status": "fail", "signature": "other"}, {"status": "timeout"},
                    {"status": "incomplete"}, {"status": "environment"}]
        stats = trial_summary(outcomes, "target")
        self.assertEqual(stats["valid"], 3)
        self.assertEqual(stats["frequency"], 1 / 3)
        self.assertEqual(stats["different"], 1)
        self.assertFalse(accepted(stats, 6, 0.1, None))
        self.assertIsNone(trial_summary([{"status": "timeout"}], "target")["frequency"])

    def test_acceptance_point_and_bound_are_distinct(self):
        stats = trial_summary([{"status": "fail", "signature": "x"}] * 3, "x")
        self.assertTrue(accepted(stats, 3, 1, None))
        self.assertFalse(accepted(stats, 3, 1, 0.8))

    def test_dependency_closure_and_source_preserved(self):
        case = fixture("false-eof", length=6, density="dense")
        original = copy.deepcopy(case)
        graph = Workload(case)
        self.assertEqual(graph.prune((0, 1, 3, 4, 5)), (0, 1))
        self.assertFalse(graph.valid((0, 2)))
        self.assertFalse(graph.valid((1, 0)))
        with self.assertRaises(ValueError):
            graph.candidate((0, 2))
        reduced = graph.candidate((0, 1))
        reduced["operations"][0]["op"] = "changed"
        self.assertEqual(case, original)
        self.assertEqual(graph.source, original)

    def test_invalid_references_cycles_and_worker_conflicts(self):
        case = fixture("false-eof", length=4, density="none")
        for edges in [
            [{"operation": 1, "requires": 9, "kind": "HARD_STRUCTURAL"}],
            [{"operation": 0, "requires": 1, "kind": "HARD_STRUCTURAL"},
             {"operation": 1, "requires": 0, "kind": "HARD_STRUCTURAL"}],
            [{"operation": 0, "requires": 0, "kind": "HARD_STRUCTURAL"}],
        ]:
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                Workload({**case, "dependencies": edges})
        with self.assertRaisesRegex(ValueError, "program order"):
            Workload({**case, "worker_ids": [0] * 4, "dependencies": [
                {"operation": 0, "requires": 2, "kind": "CONTRACT_REQUIRED"}]})

    def test_heuristics_do_not_restrict_candidates(self):
        case = fixture("false-eof", length=4, density="none")
        case["dependencies"] = [{"operation": 0, "requires": 1, "kind": "CONSERVATIVE_INFERRED"}]
        self.assertTrue(Workload(case).valid((0,)))

    def test_all_strategies_find_known_reproducer(self):
        case = fixture("false-eof", length=6, density="none")
        original = copy.deepcopy(case)
        for strategy in ("single", "chunk", "legacy", "dependency", "reproduction", "dradd"):
            with self.subTest(strategy=strategy):
                result = reduce(case, Fake(), strategy, trials=3)
                self.assertEqual(result["outcome"], "SUCCESS_REPRODUCER")
                self.assertEqual(result["reduced_operations"], 1)
                self.assertLessEqual(result["actual_executions"], 120)
                json.dumps(result, allow_nan=False)
        self.assertEqual(case, original)

    def test_budget_reserves_confirmation(self):
        result = reduce(fixture("false-eof"), Fake(), trials=3, max_executions=6)
        self.assertEqual(result["search_state"], "SEARCH_BUDGET_EXHAUSTED")
        self.assertEqual(result["actual_executions"], 6)
        self.assertEqual(result["groups"][-1]["phase"], "confirmation")

    def test_unrelated_incomplete_and_environment_results(self):
        for trial, state in [({"status": "fail", "signature": "other"}, "DIFFERENT_FAILURE"),
                             ({"status": "timeout"}, "INCOMPLETE_EXECUTION"),
                             ({"status": "environment"}, "ENVIRONMENT_ERROR"),
                             ({"status": "pass"}, "TARGET_FAILURE_NOT_REPRODUCED")]:
            with self.subTest(state=state):
                result = reduce(fixture("false-eof"), Fake([trial]), trials=3)
                self.assertEqual(result["outcome"], state)
                self.assertEqual(result["actual_executions"], 3)

    def test_nonmonotone_predicate_is_not_assumed_monotone(self):
        class Nonmonotone(Fake):
            def execute(self, workload, seed):
                return {"status": "fail" if len(workload["operations"]) % 2 == 0 else "pass",
                        "signature": self.signature}
        result = reduce(fixture("false-eof", length=6), Nonmonotone(), "single", trials=2)
        self.assertEqual(result["reduced_operations"], 6)
        self.assertTrue(result["confirmed"])

    def test_fixed_samples_and_no_invalid_trial_acceptance(self):
        mixed = Fake([{"status": "fail", "signature": "target"}, {"status": "timeout"}])
        result = reduce(fixture("false-eof"), mixed, trials=4, threshold=0.1)
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["statistics"]["valid"], 2)
        self.assertEqual(result["statistics"]["frequency"], 1)

    def test_real_simulator_fixtures(self):
        for fault in ("false-eof", "reverse-read", "resize-loss", "wrong-eagain", "short-write",
                      "capacity-corruption", "clear-noop"):
            with self.subTest(fault=fault):
                case = fixture(fault, length=6, density="none")
                result = reduce(case, FIFOAdapter(fault), trials=2, max_executions=40)
                self.assertTrue(result["confirmed"])
        control = reduce(fixture("none"), FIFOAdapter(), trials=2)
        self.assertFalse(control["confirmed"])

    def test_second_target(self):
        case = {"workers": 1, "worker_ids": [0] * 5, "operations": [
            {"op": "noop"}, {"op": "put"}, {"op": "delete"}, {"op": "noop"}, {"op": "get"}]}
        result = reduce(case, RegisterAdapter(), trials=2)
        self.assertEqual(result["reduced_operations"], 3)
        self.assertTrue(result["confirmed"])

    def test_invalid_policy(self):
        for kw in ({"threshold": math.nan}, {"trials": 0}, {"max_executions": 2}, {"max_candidates": 0}):
            with self.assertRaises(ValueError):
                reduce(fixture("false-eof"), Fake(), **kw)


if __name__ == "__main__":
    unittest.main()
