"""V2 evidence semantics, bounded history trimming, and study accounting."""

import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lab.backends import SimulatedDevice
from lab.benchmark import summarize
from lab.contract import success
from lab.history import check_history, reduce_history_prefix
from lab.replay import reduce_concurrent
from lab.demo import generate_workload, main as demo_main
from lab.concurrency import evaluate_concurrent


def event(index, op, actual, start, end):
    return {"index": index, "worker": index, "sequence": 0, "operation": op,
            "actual": actual, "started_ns": start, "finished_ns": end}


class V2Tests(unittest.TestCase):
    def test_unexpected_worker_exception_is_preserved(self):
        class Broken(SimulatedDevice):
            def apply(self, op):
                raise TypeError("fixture harness bug")
        result = evaluate_concurrent(generate_workload(steps=2, workers=2), Broken, 2)
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(len(result["history"]), 2)
        self.assertTrue(all("TypeError" in e["error"] for e in result["history"]))

    def test_invalid_backend_result_is_not_a_kernel_failure(self):
        class Broken(SimulatedDevice):
            def apply(self, op):
                return None
        result = evaluate_concurrent(generate_workload(steps=2, workers=2), Broken, 2)
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["failure_class"], "INVALID_CAPTURE")

    def test_generator_configuration_is_repeatable_and_bounded(self):
        a = generate_workload(seed=42, steps=8, workers=4, payload=257, jitter_us=100)
        self.assertEqual(a, generate_workload(seed=42, steps=8, workers=4, payload=257, jitter_us=100))
        self.assertEqual(a["worker_ids"], [0, 1, 2, 3] * 2)
        for options in ({"steps": 13}, {"workers": 1}, {"read_percent": 101},
                        {"payload": 4097}, {"jitter_us": -1}, {"capacity": 255}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                generate_workload(**options)

    def test_demo_preserves_failure_reduction_and_report(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "demo"
            self.assertEqual(demo_main(["--output", str(output), "--fault", "false-eof", "--read-percent", "100",
                                       "--write-percent", "0", "--control-percent", "0", "--repeats", "1",
                                       "--steps", "4", "--jitter-us", "10"]), 0)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["runs"][0]["classification"], "CONTRACT_MISMATCH")
            reduction = json.loads((output / "run-00" / "reduction.json").read_text())
            self.assertEqual(reduction["reduced_operations"], 1)
            html = (output / "run-00" / "report.html").read_text(encoding="utf-8")
            self.assertIn("Repeated executable replay", html)
            self.assertIn("SIMULATION", html)
            self.assertIn("not deterministic replay", html)
            recorded = json.loads((output / "run-00" / "history-reduction.json").read_text())
            self.assertEqual(recorded["classification"], "HISTORY_COUNTEREXAMPLE")
            self.assertFalse(recorded["executed"])

    def test_demo_device_unavailable_never_falls_back(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), patch("lab.demo.sys.platform", "win32"):
            output = Path(directory) / "blocked"
            self.assertEqual(demo_main(["--output", str(output), "--backend", "device", "--exclusive"]), 2)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "BLOCKED")
            self.assertEqual(manifest["backend"], "device")
            self.assertEqual(manifest["runs"], [])

    def test_control_invariants_are_rejected(self):
        write = event(0, {"op": "write", "data": "41"}, success(1), 1, 2)
        clear = event(1, {"op": "clear"}, success(), 3, 4)
        stale = event(2, {"op": "read", "count": 1}, success(1, b"A"), 5, 6)
        self.assertEqual(check_history(256, [write, clear, stale], 3)["status"], "fail")
        wrong_capacity = event(0, {"op": "capacity"}, success(512), 1, 2)
        self.assertEqual(check_history(256, [wrong_capacity], 1)["status"], "fail")
        invalid_resize = event(0, {"op": "resize", "capacity": 255}, success(), 1, 2)
        self.assertEqual(check_history(256, [invalid_resize], 1)["status"], "fail")

    def test_wrong_signature_does_not_count_as_reproduction(self):
        scenario = {"version": 1, "capacity": 256, "operations": [{"op": "capacity"}]}
        def different_failure(*args):
            return {"status": "fail", "reason": "unrelated failure", "history": []}
        _, result = reduce_concurrent(scenario, SimulatedDevice, evaluator=different_failure)
        self.assertEqual(result["replay_success_rate"], 0)
        self.assertFalse(result["confirmed"])

    def test_reduction_costs_are_counted_from_actual_trials(self):
        scenario = {"version": 1, "capacity": 256, "operations": [{"op": "read", "count": 1}] * 4}
        _, result = reduce_concurrent(scenario, lambda c: SimulatedDevice(c, "false-eof"), trials=2)
        groups = result["candidate_evidence"]
        self.assertEqual(result["total_trials"], len(groups) * 2)
        self.assertEqual(result["total_operations_executed"], sum(len(r["history"]) for g in groups for r in g["trials"]))
        self.assertGreater(result["search_transitions"], 0)

    def test_recorded_prefix_does_not_delete_overlapping_producer(self):
        history = [event(0, {"op": "read", "count": 1}, success(1, b"A"), 1, 10),
                   event(1, {"op": "write", "data": "41"}, success(1), 2, 3),
                   event(2, {"op": "read", "count": 1}, success(0, b""), 11, 12),
                   event(3, {"op": "capacity"}, success(256), 13, 14)]
        original = copy.deepcopy(history)
        result = reduce_history_prefix(256, history)
        self.assertEqual(result["classification"], "HISTORY_COUNTEREXAMPLE")
        self.assertEqual(result["reduced_operations"], 3)
        self.assertFalse(result["executed"])
        self.assertEqual(history, original)

    def test_passing_or_budget_limited_history_is_not_a_counterexample(self):
        history = [event(i, {"op": "capacity"}, success(256), 1, 10) for i in range(2)]
        self.assertEqual(reduce_history_prefix(256, history)["classification"], "NO_COUNTEREXAMPLE")
        self.assertEqual(reduce_history_prefix(256, history, budget=1)["classification"], "INCONCLUSIVE")

    def test_benchmark_dispersion_and_cpu_accounting(self):
        result = summarize([10, 20, 30], 1, 100, 25)
        self.assertAlmostEqual(result["round_trip_stdev_ns"], (200 / 3) ** 0.5)
        self.assertEqual(result["process_cpu_percent"], 25)


if __name__ == "__main__":
    unittest.main()
