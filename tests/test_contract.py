"""Portable tests of the oracle and evidence pipeline, not the Linux module."""
import errno
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from lab.backends import SimulatedDevice
from lab.contract import ReferenceModel, generate, validate
from lab.runner import evaluate, main, reduce_scenario


def scenario(*operations):
    return {"version": 1, "capacity": 256, "operations": list(operations)}


class ContractTests(unittest.TestCase):
    def test_explicit_boundary_contract(self):
        model = ReferenceModel(256)
        self.assertEqual(model.apply({"op": "read", "count": 0}),
                         {"ret": 0, "errno": 0, "data": ""})
        self.assertEqual(model.apply({"op": "read", "count": 1})["errno"], errno.EAGAIN)
        self.assertEqual(model.apply({"op": "write", "data": "ab" * 300})["ret"], 256)
        self.assertEqual(model.apply({"op": "write", "data": ""})["ret"], 0)
        self.assertEqual(model.apply({"op": "write", "data": "01"})["errno"], errno.EAGAIN)
        self.assertEqual(model.apply({"op": "resize", "capacity": 512})["ret"], 0)
        self.assertEqual(model.apply({"op": "write", "data": "cd" * 44})["ret"], 44)
        self.assertEqual(model.apply({"op": "resize", "capacity": 256})["errno"], errno.EMSGSIZE)
        self.assertEqual(model.apply({"op": "resize", "capacity": 255})["errno"], errno.EINVAL)
        self.assertEqual(model.apply({"op": "read", "count": 4096})["data"], "ab" * 256 + "cd" * 44)

    def test_generated_sequences(self):
        for seed in range(20):
            with self.subTest(seed=seed):
                case = generate(seed, 150)
                self.assertEqual(case, generate(seed, 150))
                self.assertEqual(evaluate(case, SimulatedDevice)["status"], "pass")

    def test_faults_detected(self):
        cases = {
            "false-eof": scenario({"op": "read", "count": 1}),
            "reverse-read": scenario({"op": "write", "data": "010203"}, {"op": "read", "count": 3}),
            "resize-loss": scenario({"op": "write", "data": "01"},
                                    {"op": "resize", "capacity": 512}, {"op": "read", "count": 1}),
        }
        for fault, case in cases.items():
            with self.subTest(fault=fault):
                result = evaluate(case, lambda capacity: SimulatedDevice(capacity, fault))
                self.assertEqual(result["status"], "fail")
                self.assertEqual(result["failure_index"], len(case["operations"]) - 1)

    def test_reduction_preserves_failure(self):
        case = scenario({"op": "capacity"}, {"op": "clear"},
                        {"op": "write", "data": "010203"},
                        {"op": "capacity"}, {"op": "read", "count": 3}, {"op": "clear"})
        factory = lambda capacity: SimulatedDevice(capacity, "reverse-read")
        reduced, report = reduce_scenario(case, factory)
        self.assertTrue(report["confirmed"])
        self.assertEqual(len(reduced["operations"]), 2)
        self.assertLessEqual(report["attempts"], report["budget"])
        with self.assertRaises(ValueError):
            reduce_scenario(case, SimulatedDevice)

    def test_environment_failure_is_inconclusive(self):
        def unavailable(capacity):
            raise OSError(errno.ENODEV, "device disappeared")
        result = evaluate(scenario({"op": "capacity"}), unavailable)
        self.assertEqual(result["status"], "inconclusive")

    def test_rejects_malformed_input(self):
        for op in ({"op": "read", "count": -1}, {"op": "resize", "capacity": True},
                   {"op": "write", "data": "xx"}, {"op": "write", "data": "AA"},
                   {"op": "clear", "extra": 1}, {"op": "unknown"}, {"op": []}):
            with self.subTest(op=op), self.assertRaises(ValueError):
                validate(scenario(op))

    def test_artifacts_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "first"
            self.assertEqual(main(["--steps", "20", "--output", str(output)]), 0)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertFalse(manifest["kernel_validated"])
            self.assertEqual(manifest["operations_observed"], 20)
            replay = Path(directory) / "replay"
            self.assertEqual(main(["--scenario", str(output / "scenario.json"),
                                   "--output", str(replay)]), 0)
            events = [json.loads(line) for line in (output / "history.jsonl").read_text().splitlines()]
            self.assertEqual(len(events), 20)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--output", str(output)])

    def test_missing_device_environment_saves_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "unavailable"
            self.assertEqual(main(["--backend", "device", "--exclusive",
                                   "--abi-program", str(Path(directory) / "missing-helper"),
                                   "--output", str(output)]), 2)
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(result["status"], "inconclusive")
            self.assertIn("error", result)
            self.assertEqual((output / "history.jsonl").read_text(), "")

    def test_device_requires_explicit_exclusive_use(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "not-created"
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--backend", "device", "--output", str(output)])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
