"""Explicit research adapters and controlled faults, never discovered kernel bugs."""

import errno
import random
import time

from .backends import LinuxDevice, SimulatedDevice
from .concurrency import evaluate_concurrent, validate_worker_plan
from .contract import failure, success

FAULTS = ("none", "false-eof", "reverse-read", "resize-loss", "wrong-eagain",
          "short-write", "capacity-corruption", "clear-noop", "intermittent-eof")


class ResearchDevice(SimulatedDevice):
    def __init__(self, capacity, fault, active=True, delay_us=0):
        super().__init__(capacity, fault if active else "none")
        self.delay_us = delay_us

    def _apply_locked(self, op):
        if self.delay_us:
            time.sleep(self.delay_us / 1e6)
        if self.fault == "wrong-eagain" and op["op"] == "read" and op["count"] and not self.queue:
            return failure(errno.EINVAL)
        if self.fault == "short-write" and op["op"] == "write" and op["data"]:
            return super()._apply_locked({**op, "data": op["data"][:-2]})
        if self.fault == "capacity-corruption" and op["op"] == "capacity":
            return success(self.capacity + 1)
        if self.fault == "clear-noop" and op["op"] == "clear":
            return success()
        if self.fault == "intermittent-eof" and op["op"] == "read" and op["count"] and not self.queue:
            return success(0, b"")
        return super()._apply_locked(op)


class FIFOAdapter:
    signature = "FIFO:NO_LEGAL_ORDER"

    def __init__(self, fault="none", probability=0.7, delay_us=0, search_budget=10000,
                 device=None, abi_program=None, exclusive=False):
        if fault not in FAULTS or not 0 <= probability <= 1 or not 0 <= delay_us <= 10000:
            raise ValueError("invalid fixture configuration")
        if device and (not exclusive or fault != "none"):
            raise ValueError("device requires exclusive acknowledgement and no simulated fault")
        self.fault, self.probability, self.delay_us = fault, probability, delay_us
        self.search_budget = search_budget
        self.device, self.abi_program = device, abi_program

    def validate(self, workload):
        validate_worker_plan(workload, workload["workers"])

    def metadata(self):
        return {"target": "ringbuf_char" if self.device else "fifo-simulator",
                "evidence_kind": "LINUX_DEVICE_EXECUTION" if self.device else "SIMULATED_FAULT",
                "fault": self.fault, "intermittent_probability": self.probability,
                "delay_us": self.delay_us, "search_budget": self.search_budget,
                "device": self.device, "abi_program": str(self.abi_program) if self.abi_program else None,
                "schedule": "uncontrolled OS threads with start barrier"}

    def execute(self, workload, trial_seed):
        active = self.fault != "intermittent-eof" or random.Random(trial_seed).random() < self.probability
        factory = (lambda capacity: LinuxDevice(capacity, self.device, self.abi_program)) if self.device else (
            lambda capacity: ResearchDevice(capacity, self.fault, active, self.delay_us))
        result = evaluate_concurrent(workload, factory, workload["workers"], self.search_budget)
        if result["status"] == "fail":
            result["signature"] = self.signature
        elif result["status"] == "inconclusive":
            result["status"] = "environment" if result.get("failure_class") == "EXECUTION_ERROR" else "incomplete"
        result["operations_executed"] = len(result.get("history", []))
        return result


class RegisterAdapter:
    """Independent sequential key/value target; demonstrates engine reuse only."""
    signature = "REGISTER:STALE_AFTER_DELETE"

    def validate(self, workload):
        if any(w != 0 for w in workload["worker_ids"]):
            raise ValueError("register adapter supports one active worker only")
        for op in workload["operations"]:
            if op not in ({"op": "put"}, {"op": "delete"}, {"op": "get"}, {"op": "noop"}):
                raise ValueError("invalid register operation")

    def metadata(self):
        return {"target": "one-key-register", "evidence_kind": "SIMULATED_FAULT",
                "fault": "delete-noop", "schedule": "sequential reference adapter"}

    def execute(self, workload, trial_seed):
        expected = actual = None
        history = []
        mismatch = False
        for op in workload["operations"]:
            if op["op"] == "put":
                expected = actual = 1
            elif op["op"] == "delete":
                expected = None
            elif op["op"] == "get":
                mismatch |= expected != actual
            history.append({"operation": op, "expected": expected, "actual": actual})
        return {"status": "fail" if mismatch else "pass", "signature": self.signature if mismatch else None,
                "history": history, "operations_executed": len(history)}


def fixture(fault, seed=0, length=8, workers=2, density="sparse", delay_us=0):
    if fault not in FAULTS or density not in ("none", "sparse", "dense") or not 4 <= length <= 12:
        raise ValueError("invalid fixture")
    cores = {
        "none": [{"op": "read", "count": 1}],
        "false-eof": [{"op": "read", "count": 1}],
        "wrong-eagain": [{"op": "read", "count": 1}],
        "intermittent-eof": [{"op": "read", "count": 1}],
        "short-write": [{"op": "write", "data": "010203"}],
        "capacity-corruption": [{"op": "capacity"}],
        "reverse-read": [{"op": "write", "data": "010203"}, {"op": "read", "count": 3}],
        "resize-loss": [{"op": "write", "data": "010203"}, {"op": "resize", "capacity": 512},
                        {"op": "read", "count": 3}],
        "clear-noop": [{"op": "write", "data": "010203"}, {"op": "clear"}, {"op": "read", "count": 3}],
    }
    rng = random.Random(seed)
    positions = sorted(rng.sample(range(length), len(cores[fault])))
    core = iter(cores[fault])
    operations = [next(core) if i in positions else {"op": "capacity"} for i in range(length)]
    owners = [0 if i in positions else 1 + i % (workers - 1) for i in range(length)]
    dependencies = []
    # Artificial declared inclusion constraints, not inferred read/write causality.
    # All methods receive identical constraints; dense cases intentionally limit reduction.
    for i in range(1, length):
        if density == "dense" or (density == "sparse" and i % 3 == 0):
            dependencies.append({"operation": i, "requires": i - 1, "kind": "CONTRACT_REQUIRED"})
    return {"version": 1, "capacity": 256, "seed": seed, "workers": workers,
            "worker_ids": owners, "operations": operations, "dependencies": dependencies,
            "fixture": {"fault": fault, "density": density, "delay_us": delay_us,
                        "label": "INTERMITTENT_INJECTED_FAULT" if fault == "intermittent-eof" else
                                 "DETERMINISTIC_INJECTED_FAULT" if fault != "none" else "CORRECT_CONTROL"}}
