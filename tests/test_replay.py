"""Reduction must replay workloads, preserve workers, and retain uncertainty."""

from contextlib import redirect_stderr, redirect_stdout
import io
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from lab.backends import SimulatedDevice
from lab.concurrency import evaluate_concurrent
from lab.history import main as recheck
from lab.runner import main as run
from lab.replay import main as replay_cli, reduce_concurrent
from lab.experiment import fixture, main as experiment_cli


class ReplayTests(unittest.TestCase):
    def test_runner_accepts_reduced_workload_with_idle_workers(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            source = root / "reduced.json"
            source.write_text(json.dumps({"version": 1, "capacity": 256,
                                         "worker_ids": [1],
                                         "operations": [{"op": "read", "count": 1}]}))
            output = root / "run"
            self.assertEqual(run(["--scenario", str(source), "--workers", "3",
                                  "--fault", "false-eof", "--output", str(output)]), 1)
            self.assertEqual(recheck([str(output)]), 1)
            history = [json.loads(line) for line in (output / "history.jsonl").read_text().splitlines()]
            self.assertEqual([(e["worker"], e["sequence"]) for e in history], [(1, 0)])

    def test_runner_rejects_invalid_plan_before_creating_bundle(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            source = root / "scenario.json"
            for index, owners in enumerate(([0], [0, 2], [True, 1], "01")):
                source.write_text(json.dumps({"version": 1, "capacity": 256,
                                             "worker_ids": owners,
                                             "operations": [{"op": "capacity"}] * 2}))
                output = root / f"invalid-{index}"
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    run(["--scenario", str(source), "--workers", "2", "--output", str(output)])
                self.assertEqual(caught.exception.code, 2)
                self.assertFalse(output.exists())

    def test_runner_does_not_silently_discard_worker_plan(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            source = root / "scenario.json"
            source.write_text(json.dumps(fixture("reverse-read", 0)))
            output = root / "sequential"
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                run(["--scenario", str(source), "--output", str(output)])
            self.assertEqual(caught.exception.code, 2)
            self.assertFalse(output.exists())

    def test_cli_retains_evidence_and_replays_reduced_scenario(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            scenario = root / "scenario.json"
            scenario.write_text(json.dumps(fixture("false-eof", 0)))
            output = root / "first"
            self.assertEqual(replay_cli(["--scenario", str(scenario), "--fault", "false-eof",
                                         "--output", str(output)]), 0)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["backend"], "simulated")
            self.assertTrue(manifest["source_sha256"])
            for name, digest in manifest["source_sha256"].items():
                self.assertEqual(hashlib.sha256((output / manifest["source_snapshot"] / name).read_bytes()).hexdigest(), digest)
            result = json.loads((output / "reduction.json").read_text())
            self.assertEqual(result["reduced_operations"], 1)
            self.assertEqual(replay_cli(["--scenario", str(output / "reduced.json"),
                                         "--fault", "false-eof", "--output", str(root / "second")]), 0)

    def test_replay_runs_from_saved_source(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            source = root / "scenario.json"
            source.write_text(json.dumps(fixture("false-eof", 0)))
            output = root / "captured"
            self.assertEqual(replay_cli(["--scenario", str(source), "--fault", "false-eof",
                                         "--output", str(output)]), 0)
            result = subprocess.run([sys.executable, "-m", "lab.replay", "--scenario",
                                     str(output / "reduced.json"), "--fault", "false-eof",
                                     "--output", str(root / "restored")],
                                    cwd=output / "source", capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = json.loads((root / "restored" / "reduction.json").read_text())
            self.assertEqual(saved["outcome"], "EXECUTABLE_REPRODUCER_FOUND")
            self.assertEqual(saved["reduced_operations"], 1)

    def test_study_retains_source_and_all_results(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "study"
            self.assertEqual(experiment_cli(["--output", str(output)]), 0)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["runs"], 40)
            self.assertIn("lab/experiment.py", manifest["source_sha256"])
            for name, digest in manifest["source_sha256"].items():
                self.assertEqual(hashlib.sha256((output / "source" / name).read_bytes()).hexdigest(), digest)
            rows = json.loads((output / "results.json").read_text())["rows"]
            self.assertEqual(len(rows), 40)
            for row in rows:
                self.assertTrue((output / f"{row['fixture']}-{row['seed']}-{row['strategy']}.json").is_file())

    def test_experiment_fixtures_have_expected_verdicts(self):
        for fault in ("none", "false-eof", "reverse-read", "resize-loss"):
            for seed in range(5):
                with self.subTest(fault=fault, seed=seed):
                    scenario = fixture(fault, seed)
                    result = evaluate_concurrent(scenario, lambda c: SimulatedDevice(c, fault), 2)
                    self.assertEqual(result["status"], "pass" if fault == "none" else "fail")

    def test_invalid_reduction_limits(self):
        scenario = fixture("false-eof", 0)
        for options in ({"workers": 0}, {"budget": 0}, {"trials": 0},
                        {"search_budget": 0}, {"strategy": "unknown"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                reduce_concurrent(scenario, SimulatedDevice, **options)

    def test_both_strategies_reexecute_stateful_workload(self):
        scenario = {"version": 1, "capacity": 256, "worker_ids": [0, 1, 0, 1],
                    "operations": [{"op": "write", "data": "4142"}, {"op": "capacity"},
                                   {"op": "read", "count": 2}, {"op": "capacity"}]}
        for strategy in ("single", "chunk"):
            reduced, result = reduce_concurrent(scenario, lambda c: SimulatedDevice(c, "reverse-read"),
                                                strategy=strategy, trials=2)
            self.assertEqual(result["outcome"], "EXECUTABLE_REPRODUCER_FOUND")
            self.assertEqual(reduced["worker_ids"], [0, 0])
            self.assertEqual([op["op"] for op in reduced["operations"]], ["write", "read"])
            self.assertEqual(result["confirmation_counts"]["fail"], 2)
            self.assertFalse(result["kernel_validated"])

    def test_correct_device_is_not_a_reproducer(self):
        scenario = {"version": 1, "capacity": 256, "operations": [{"op": "read", "count": 1}] * 2}
        _, result = reduce_concurrent(scenario, SimulatedDevice)
        self.assertEqual(result["outcome"], "REPRODUCTION_FAILED")
        self.assertEqual(result["attempts"], 0)

    def test_budget_and_uncertain_replay(self):
        scenario = {"version": 1, "capacity": 256, "operations": [{"op": "read", "count": 1}] * 4}
        _, result = reduce_concurrent(scenario, lambda c: SimulatedDevice(c, "false-eof"), budget=1)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(len(result["candidate_evidence"]), 3)
        def uncertain(*args):
            return {"status": "inconclusive", "reason": "search budget exhausted", "history": []}
        _, result = reduce_concurrent(scenario, SimulatedDevice, evaluator=uncertain)
        self.assertEqual(result["outcome"], "INCONCLUSIVE")
        self.assertFalse(result["confirmed"])

    def test_confirmation_failure_is_not_success(self):
        scenario = {"version": 1, "capacity": 256, "operations": [{"op": "capacity"}]}
        outcomes = iter([{"status": "fail", "reason": "no legal FIFO ordering", "history": []},
                         {"status": "pass", "history": []}])
        _, result = reduce_concurrent(scenario, SimulatedDevice, trials=1,
                                      evaluator=lambda *args: next(outcomes))
        self.assertEqual(result["outcome"], "REPRODUCTION_FAILED")

    def test_cleanup_failure_cannot_become_offline_pass(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "run"
            self.assertEqual(run(["--workers", "2", "--steps", "4", "--output", str(output)]), 0)
            manifest = json.loads((output / "manifest.json").read_text())
            manifest["status"] = "inconclusive"
            (output / "manifest.json").write_text(json.dumps(manifest))
            (output / "result.json").write_text(json.dumps({
                "status": "inconclusive", "error": "OSError: capacity restore failed"}))
            self.assertEqual(recheck([str(output)]), 2)

    def test_explicit_worker_assignment_and_idle_worker(self):
        scenario = {"version": 1, "capacity": 256, "worker_ids": [1, 1],
                    "operations": [{"op": "write", "data": "4142"}, {"op": "read", "count": 2}]}
        result = evaluate_concurrent(scenario, SimulatedDevice, 3)
        self.assertEqual(result["status"], "pass")
        self.assertEqual([(e["worker"], e["sequence"]) for e in result["history"]], [(1, 0), (1, 1)])
        scenario["worker_ids"] = [1, 3]
        with self.assertRaises(ValueError):
            evaluate_concurrent(scenario, SimulatedDevice, 3)

    def test_cleanup_and_worker_faults_remain_inconclusive(self):
        closed = []

        class Broken(SimulatedDevice):
            def apply(self, operation):
                raise OSError("injected worker error")

            def __exit__(self, *args):
                closed.append(True)
                raise OSError("injected cleanup error")

        scenario = {"version": 1, "capacity": 256, "operations": [{"op": "capacity"}] * 2}
        result = evaluate_concurrent(scenario, Broken, 2)
        self.assertEqual(result["status"], "inconclusive")
        self.assertIn("cleanup", result["error"])
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
