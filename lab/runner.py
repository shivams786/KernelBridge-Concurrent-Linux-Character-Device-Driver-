"""Run, replay, and reduce sequential device-contract scenarios."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

from .backends import LinuxDevice, SimulatedDevice
from .contract import ReferenceModel, generate, validate
from .concurrency import evaluate_concurrent, validate_worker_plan

ROOT = Path(__file__).resolve().parents[1]


def evaluate(scenario, factory, record=None):
    validate(scenario)
    model = ReferenceModel(scenario["capacity"])
    history = []
    result = {"status": "pass", "history": history, "signature": None}
    try:
        with factory(scenario["capacity"]) as device:
            for index, op in enumerate(scenario["operations"]):
                expected = model.apply(op)
                started = time.perf_counter_ns()
                actual = device.apply(op)
                fields = sorted(key for key in expected.keys() | actual.keys()
                                if expected.get(key) != actual.get(key))
                history.append({"index": index, "operation": op, "expected": expected,
                                "actual": actual, "elapsed_ns": time.perf_counter_ns() - started})
                if record is not None:
                    record(history[-1])
                if fields:
                    result.update(status="fail", failure_index=index,
                                  signature={"operation": op["op"], "fields": fields,
                                             "expected_errno": expected["errno"],
                                             "actual_errno": actual["errno"]})
                    break
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        result.update(status="inconclusive", signature=None,
                      error=f"{type(exc).__name__}: {exc}")
    return result


def reduce_scenario(scenario, factory, budget=100):
    """Bounded deletion reduction; preserve observed signature, not root-cause proof."""
    original = evaluate(scenario, factory)
    if original["status"] != "fail":
        raise ValueError("reduction requires a reproducible contract failure")
    operations = scenario["operations"][:original["failure_index"] + 1]
    attempts = 0
    granularity = 2
    while len(operations) > 1 and attempts < budget:
        chunk = (len(operations) + granularity - 1) // granularity
        changed = False
        for start in range(0, len(operations), chunk):
            candidate = operations[:start] + operations[start + chunk:]
            if not candidate:
                continue
            attempts += 1
            observed = evaluate({**scenario, "operations": candidate}, factory)
            if observed["status"] == "fail" and observed["signature"] == original["signature"]:
                operations = candidate
                granularity = max(2, granularity - 1)
                changed = True
                break
            if attempts >= budget:
                break
        if not changed:
            if granularity >= len(operations):
                break
            granularity = min(len(operations), granularity * 2)
    reduced = {**scenario, "operations": operations}
    confirmed = evaluate(reduced, factory)
    return reduced, {"attempts": attempts, "budget": budget,
                     "original_operations": len(scenario["operations"]),
                     "reduced_operations": len(operations),
                     "confirmed": confirmed["status"] == "fail" and
                     confirmed["signature"] == original["signature"],
                     "confirmation": confirmed}


def git_output(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["simulated", "device"], default="simulated")
    parser.add_argument("--fault", choices=["none", "false-eof", "reverse-read", "resize-loss"], default="none")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--workers", type=int, default=1, help="1 sequential; 2..4 concurrent, at most 12 operations")
    parser.add_argument("--search-budget", type=int, default=10000)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument("--device", default="/dev/ringbuf_char")
    parser.add_argument("--abi-program", type=Path, default=ROOT / "userspace" / "abi_dump")
    parser.add_argument("--exclusive", action="store_true",
                        help="acknowledge exclusive disposable device use; buffer is cleared")
    parser.add_argument("--reduce", action="store_true")
    args = parser.parse_args(argv)
    if args.workers not in (1, 2, 3, 4) or not 1 <= args.search_budget <= 100000:
        parser.error("workers must be 1..4 and search budget 1..100000")
    if args.workers > 1 and args.reduce:
        parser.error("reduction currently supports sequential runs only")
    if args.backend == "device" and (not args.exclusive or args.fault != "none"):
        parser.error("device runs require --exclusive and --fault none")
    try:
        if args.scenario:
            if args.scenario.stat().st_size > 90_000_000:
                raise ValueError("scenario file exceeds 90 MB")
            scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
        else:
            scenario = generate(args.seed, args.steps)
        validate(scenario)
        if args.workers > 1:
            validate_worker_plan(scenario, args.workers)
        elif "worker_ids" in scenario:
            raise ValueError("worker_ids requires concurrent mode; specify --workers 2..4")
        args.output.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    # Persist inputs before opening the device, including for incomplete runs.
    save_json(args.output / "scenario.json", scenario)
    hashes = {}
    for pattern in ("lab/*.py", "kernel/*.c", "kernel/*.h", "include/*.h", "userspace/abi_dump.c"):
        for source in ROOT.glob(pattern):
            hashes[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {"schema_version": 1, "started_utc": datetime.now(timezone.utc).isoformat(),
                "backend": args.backend, "fixture_fault": args.fault,
                "kernel_validated": False, "platform": platform.platform(),
                "python": sys.version, "git_commit": git_output("rev-parse", "HEAD"),
                "git_status": git_output("status", "--porcelain"), "source_sha256": hashes,
                "scope": ("sequential nonblocking byte-stream contract" if args.workers == 1 else
                          "bounded concurrent nonblocking byte-stream contract"),
                "workers": args.workers, "search_budget": args.search_budget,
                "clock": "perf_counter", "clock_resolution_seconds": time.get_clock_info("perf_counter").resolution,
                "status": "running", "device": args.device if args.backend == "device" else None}
    save_json(args.output / "manifest.json", manifest)
    if args.backend == "simulated":
        factory = lambda capacity: SimulatedDevice(capacity, args.fault)
    else:
        factory = lambda capacity: LinuxDevice(capacity, args.device, args.abi_program)
    with (args.output / "history.jsonl").open("w", encoding="utf-8") as stream:
        def record(event):
            stream.write(json.dumps(event) + "\n")
            stream.flush()
        if args.workers == 1:
            result = evaluate(scenario, factory, record)
        else:
            result = evaluate_concurrent(scenario, factory, args.workers, args.search_budget, record)
    if args.reduce and result["status"] == "fail":
        try:
            reduced, reduction = reduce_scenario(scenario, factory)
            save_json(args.output / "reduced.json", reduced)
            save_json(args.output / "reduction.json", reduction)
        except ValueError as exc:
            save_json(args.output / "reduction.json", {"confirmed": False, "error": str(exc)})
    save_json(args.output / "result.json", {k: v for k, v in result.items() if k != "history"})
    manifest.update(status=result["status"], operations_observed=len(result["history"]),
                    finished_utc=datetime.now(timezone.utc).isoformat())
    # Passing the declared subset must never be labeled overall kernel validation.
    save_json(args.output / "manifest.json", manifest)
    print(f"{result['status'].upper()}: {args.backend}, {len(result['history'])} operations; {args.output}")
    return {"pass": 0, "fail": 1, "inconclusive": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
