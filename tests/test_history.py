"""Exercise real-time ordering, ambiguous histories, and bounded search."""

from contextlib import redirect_stderr, redirect_stdout
import errno
import io
import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest

from lab.backends import SimulatedDevice
from lab.concurrency import evaluate_concurrent
from lab.contract import ReferenceModel, failure, generate, success
from lab.history import check_history, main as recheck
from lab.runner import main


def event(index, operation, actual, start=1, end=10, worker=None, sequence=0):
    return {"index": index, "worker": index if worker is None else worker,
            "sequence": sequence, "started_ns": start, "finished_ns": end,
            "operation": operation, "actual": actual}


def exhaustive(history):
    """Small independent permutation oracle to cross-check the DFS implementation."""
    for ordering in itertools.permutations(range(len(history))):
        positions = {value: i for i, value in enumerate(ordering)}
        if any(positions[i] > positions[j]
               for i, a in enumerate(history) for j, b in enumerate(history)
               if a["finished_ns"] < b["started_ns"]):
            continue
        model = ReferenceModel(256)
        if all(model.apply(history[i]["operation"]) == history[i]["actual"] for i in ordering):
            return True
    return False


class HistoryTests(unittest.TestCase):
    def test_overlap_can_have_multiple_valid_orders(self):
        history = [event(0, {"op": "write", "data": "41"}, success(1)),
                   event(1, {"op": "write", "data": "42"}, success(1)),
                   event(2, {"op": "read", "count": 2}, success(2, b"BA"))]
        result = check_history(256, history, 3)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["witness_order"], [1, 0, 2])

    def test_real_time_must_be_preserved(self):
        history = [event(0, {"op": "write", "data": "41"}, success(1), 1, 2),
                   event(1, {"op": "read", "count": 1}, failure(errno.EAGAIN), 3, 4)]
        self.assertEqual(check_history(256, history, 2)["status"], "fail")
        history[1]["started_ns"] = 2
        self.assertEqual(check_history(256, history, 2)["status"], "pass")

    def test_program_order_breaks_clock_ties(self):
        history = [event(0, {"op": "write", "data": "41"}, success(1), 1, 2, 0, 0),
                   event(1, {"op": "read", "count": 1}, failure(errno.EAGAIN), 2, 3, 0, 1)]
        self.assertEqual(check_history(256, history, 2)["status"], "fail")

    def test_data_loss_and_duplicate_consumption(self):
        history = [event(0, {"op": "write", "data": "41"}, success(1), 1, 2),
                   event(1, {"op": "read", "count": 1}, success(1, b"A"), 3, 8),
                   event(2, {"op": "read", "count": 1}, success(1, b"A"), 3, 8)]
        self.assertEqual(check_history(256, history, 3)["status"], "fail")

    def test_budget_and_incomplete_are_inconclusive(self):
        history = [event(i, {"op": "capacity"}, success(256)) for i in range(2)]
        self.assertEqual(check_history(256, history, 2, budget=1)["status"], "inconclusive")
        self.assertEqual(check_history(256, history, 2, budget=2)["status"], "pass")
        self.assertEqual(check_history(256, history[:1], 2)["status"], "inconclusive")
        history[1]["error"] = "device disappeared"
        self.assertEqual(check_history(256, history, 2)["status"], "inconclusive")

    def test_rejects_invalid_intervals_and_indexes(self):
        bad = event(0, {"op": "capacity"}, success(256), 3, 2)
        with self.assertRaises(ValueError):
            check_history(256, [bad], 1)
        repeated = event(0, {"op": "capacity"}, success(256))
        with self.assertRaises(ValueError):
            check_history(256, [repeated, repeated], 2)

    def test_matches_exhaustive_oracle(self):
        rng = random.Random(27)
        for case in range(40):
            history = []
            model = ReferenceModel(256)
            for index, operation in enumerate(generate(case, 5)["operations"]):
                actual = model.apply(operation)
                if rng.randrange(4) == 0:
                    actual = success(7)
                start = rng.randrange(1, 10)
                history.append(event(index, operation, actual, start, start + rng.randrange(1, 8)))
            with self.subTest(case=case):
                self.assertEqual(check_history(256, history, 5)["status"] == "pass", exhaustive(history))

    def test_live_simulation_and_failure(self):
        for seed in range(12):
            with self.subTest(seed=seed):
                result = evaluate_concurrent(generate(seed, 12), SimulatedDevice, 3)
                self.assertEqual(result["status"], "pass")
                self.assertEqual(len(result["history"]), 12)
        case = {"version": 1, "capacity": 256,
                "operations": [{"op": "read", "count": 1}] * 4}
        result = evaluate_concurrent(case, lambda c: SimulatedDevice(c, "false-eof"), 2)
        self.assertEqual(result["status"], "fail")

    def test_worker_error_is_inconclusive(self):
        class BrokenDevice(SimulatedDevice):
            def apply(self, operation):
                raise OSError(errno.EIO, "fixture I/O failure")
        result = evaluate_concurrent(generate(1, 6), BrokenDevice, 2)
        self.assertEqual(result["status"], "inconclusive")

    def test_cli_evidence_and_offline_recheck(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "run"
            self.assertEqual(main(["--steps", "12", "--workers", "3", "--output", str(output)]), 0)
            self.assertEqual(recheck([str(output)]), 0)
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(sorted(result["witness_order"]), list(range(12)))
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--workers", "2", "--reduce", "--output", str(output)])

    def test_offline_recheck_can_increase_budget(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "limited"
            self.assertEqual(main(["--steps", "12", "--workers", "3", "--search-budget", "1",
                                   "--output", str(output)]), 2)
            self.assertEqual(recheck([str(output), "--budget", "10000"]), 0)
            history_path = output / "history.jsonl"
            lines = history_path.read_text().splitlines()
            tampered = json.loads(lines[0])
            tampered["operation"] = {"op": "clear", "extra": True}
            lines[0] = json.dumps(tampered)
            history_path.write_text("\n".join(lines) + "\n")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                recheck([str(output)])

    def test_offline_rejects_changed_worker_ownership(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "run"
            self.assertEqual(main(["--steps", "4", "--workers", "2", "--output", str(output)]), 0)
            history_path = output / "history.jsonl"
            events = [json.loads(line) for line in history_path.read_text().splitlines()]
            for item in events:
                item["worker"] = 1 - item["worker"]
            history_path.write_text("\n".join(json.dumps(item) for item in events) + "\n")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                recheck([str(output)])
            self.assertEqual(caught.exception.code, 2)

    def test_offline_checks_explicit_worker_plan(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            scenario = {"version": 1, "capacity": 256, "worker_ids": [1, 1],
                        "operations": [{"op": "capacity"}, {"op": "capacity"}]}
            source = root / "scenario.json"
            source.write_text(json.dumps(scenario))
            output = root / "run"
            self.assertEqual(main(["--scenario", str(source), "--workers", "2", "--output", str(output)]), 0)
            self.assertEqual(recheck([str(output)]), 0)
            scenario["worker_ids"] = [0, 0]
            (output / "scenario.json").write_text(json.dumps(scenario))
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                recheck([str(output)])
            self.assertEqual(caught.exception.code, 2)

    def test_unknown_inconclusive_reason_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "run"
            self.assertEqual(main(["--steps", "4", "--workers", "2", "--output", str(output)]), 0)
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["status"] = "inconclusive"
            manifest_path.write_text(json.dumps(manifest))
            (output / "result.json").write_text(json.dumps({
                "status": "inconclusive", "reason": "unclassified execution problem"}))
            self.assertEqual(recheck([str(output)]), 2)

    def test_malformed_event_is_a_cli_error(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "run"
            self.assertEqual(main(["--steps", "4", "--workers", "2", "--output", str(output)]), 0)
            (output / "history.jsonl").write_text("null\n" * 4)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                recheck([str(output)])
            self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
