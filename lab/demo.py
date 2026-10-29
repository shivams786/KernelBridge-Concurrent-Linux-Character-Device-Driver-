"""Bounded generate/execute/check/reduce/report workflow; no backend fallback."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import random
import sys

from .backends import SimulatedDevice
from .contract import validate
from .history import reduce_history_prefix
from .replay import reduce_concurrent
from .report import main as report_main
from .runner import ROOT, save_json
from .validate_linux import run_step, snapshot


def generate_workload(seed=1, steps=12, workers=3, payload=64, capacity=256,
                      read_percent=35, write_percent=35, control_percent=20, jitter_us=0):
    values = (seed, steps, workers, payload, capacity, read_percent, write_percent, control_percent, jitter_us)
    if any(type(value) is not int for value in values):
        raise ValueError("workload settings must be integers")
    if (not 1 <= steps <= 12 or not 2 <= workers <= 4 or not 0 <= payload <= 4096 or
            not 256 <= capacity <= 65536 or not 0 <= jitter_us <= 10000 or
            min(read_percent, write_percent, control_percent) < 0 or
            read_percent + write_percent + control_percent > 100):
        raise ValueError("invalid bounded workload configuration")
    rng = random.Random(seed)
    operations = []
    for _ in range(steps):
        choice = rng.randrange(100)
        if choice < read_percent:
            op = {"op": "read", "count": payload}
        elif choice < read_percent + write_percent:
            op = {"op": "write", "data": bytes(rng.randrange(256) for _ in range(payload)).hex()}
        elif choice < read_percent + write_percent + control_percent:
            op = rng.choice([{"op": "clear"}, {"op": "resize", "capacity": 256},
                             {"op": "resize", "capacity": 512}, {"op": "resize", "capacity": 255}])
        else:
            op = {"op": "capacity"}
        operations.append(op)
    return validate({"version": 1, "seed": seed, "capacity": capacity, "jitter_us": jitter_us,
                     "worker_ids": [i % workers for i in range(steps)], "operations": operations})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=["simulated", "device"], default="simulated")
    parser.add_argument("--fault", choices=["none", "false-eof", "reverse-read", "resize-loss"], default="none")
    for name, default in (("seed", 1), ("steps", 12), ("workers", 3), ("payload", 64),
                          ("capacity", 256), ("read-percent", 35), ("write-percent", 35),
                          ("control-percent", 20), ("jitter-us", 0), ("repeats", 3)):
        parser.add_argument("--" + name, type=int, default=default)
    parser.add_argument("--exclusive", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 20:
        parser.error("repeats must be 1..20")
    if args.backend == "device" and (not args.exclusive or args.fault != "none"):
        parser.error("device mode requires --exclusive and --fault none")
    try:
        scenario = generate_workload(args.seed, args.steps, args.workers, args.payload, args.capacity,
                                     args.read_percent, args.write_percent, args.control_percent, args.jitter_us)
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    sources = snapshot(ROOT, output / "source", [p.relative_to(ROOT).as_posix()
                       for p in (ROOT / "lab").iterdir() if p.suffix in (".py", ".css", ".js")])
    manifest = {"status": "RUNNING", "backend": args.backend, "kernel_validated": False,
                "settings": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                "started_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
                "source_snapshot": "source", "source_files": sources,
                "diagnostics": {"status": "BLOCKED" if args.backend == "device" else "NOT_APPLICABLE",
                                "reason": "kernel diagnostics require separate Linux validation"}, "runs": []}
    save_json(output / "manifest.json", manifest)
    save_json(output / "scenario.json", scenario)
    if args.backend == "device" and sys.platform != "linux":
        manifest.update(status="BLOCKED", reason="Linux device execution unavailable; no simulation fallback")
        save_json(output / "manifest.json", manifest)
        print(manifest["reason"])
        return 2
    for repeat in range(args.repeats):
        run = output / f"run-{repeat:02d}"
        command = [sys.executable, "-m", "lab.runner", "--scenario", str(output / "scenario.json"),
                   "--workers", str(args.workers), "--backend", args.backend, "--fault", args.fault,
                   "--output", str(run)] + (["--exclusive"] if args.exclusive else [])
        step = run_step(f"run-{repeat:02d}", command, ROOT, output, 60)
        if step.get("exit_code") not in (0, 1, 2) or not (run / "result.json").exists():
            manifest["runs"].append({"classification": "HARNESS_FAILURE", "step": step})
            continue
        result = json.loads((run / "result.json").read_text())
        run_manifest_path = run / "manifest.json"
        run_manifest = json.loads(run_manifest_path.read_text())
        run_manifest.update(reproduction_command=command, diagnostics=manifest["diagnostics"],
                            module_identity={"status": "UNVERIFIED" if args.backend == "device" else "NOT_APPLICABLE"})
        save_json(run_manifest_path, run_manifest)
        classification = {"pass": "CONTRACT_PASS", "fail": "CONTRACT_MISMATCH",
                          "inconclusive": "INCONCLUSIVE"}[result["status"]]
        if result["status"] == "fail" and args.backend == "simulated":
            history = [json.loads(line) for line in (run / "history.jsonl").read_text().splitlines()]
            save_json(run / "history-reduction.json", reduce_history_prefix(scenario["capacity"], history))
            reduced, reduction = reduce_concurrent(scenario, lambda c: SimulatedDevice(c, args.fault),
                                                   workers=args.workers, budget=20)
            save_json(run / "reduced.json", reduced)
            save_json(run / "reduction.json", reduction)
        report_main([str(run)])
        manifest["runs"].append({"classification": classification, "step": step,
                                  "report": f"run-{repeat:02d}/report.html"})
        save_json(output / "manifest.json", manifest)
    manifest.update(status="COMPLETE" if all(r["classification"] in ("CONTRACT_PASS", "CONTRACT_MISMATCH")
                                            for r in manifest["runs"]) else "INCONCLUSIVE",
                    finished_utc=datetime.now(timezone.utc).isoformat())
    save_json(output / "manifest.json", manifest)
    print(f"{manifest['status']}: {output}")
    return 0 if manifest["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
