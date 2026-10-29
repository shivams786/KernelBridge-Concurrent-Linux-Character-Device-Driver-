"""Compare two deletion strategies on a fixed, simulation-only fixture corpus."""

import argparse
from datetime import datetime, timezone
import platform
import random
import statistics
import sys
from pathlib import Path

from .backends import SimulatedDevice
from .replay import reduce_concurrent
from .runner import ROOT, git_output, save_json
from .validate_linux import snapshot


def fixture(fault, seed, steps=12, workers=2):
    cores = {
        "false-eof": [{"op": "read", "count": 1}],
        "reverse-read": [{"op": "write", "data": "414243"}, {"op": "read", "count": 3}],
        "resize-loss": [{"op": "write", "data": "414243"},
                        {"op": "resize", "capacity": 512}, {"op": "read", "count": 3}],
        "none": [{"op": "write", "data": "414243"}, {"op": "read", "count": 3}],
    }
    rng = random.Random(seed)
    positions = sorted(rng.sample(range(steps), len(cores[fault])))
    operations = [{"op": "capacity"} for _ in range(steps)]
    owners = [1 + i % (workers - 1) for i in range(steps)]
    for index, op in zip(positions, cores[fault]):
        operations[index] = op.copy()
        owners[index] = 0
    return {"version": 1, "capacity": 256, "seed": seed,
            "operations": operations, "worker_ids": owners}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matrix-v2", action="store_true", help="4/8/12 operations, 2/4 workers, five seeds")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    sources = snapshot(ROOT, args.output / "source",
                       [p.relative_to(ROOT).as_posix() for p in (ROOT / "lab").glob("*.py")])
    manifest = {"status": "running", "evidence_kind": "SIMULATION", "kernel_validated": False,
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "platform": platform.platform(), "python": sys.version,
                "git_commit": git_output("rev-parse", "HEAD"),
                "git_status": git_output("status", "--porcelain"),
                "source_snapshot": "source",
                "source_sha256": {name: record["working_sha256"] for name, record in sources.items()},
                "seeds": list(range(5)), "trials_per_candidate": 3,
                "candidate_budget": 100, "search_budget": 10000}
    manifest["matrix_v2"] = args.matrix_v2
    save_json(args.output / "manifest.json", manifest)
    jobs = [(fault, seed, strategy, steps, workers) for fault in ("none", "false-eof", "reverse-read", "resize-loss")
            for seed in range(5) for strategy in ("single", "chunk")
            for steps in ([4, 8, 12] if args.matrix_v2 else [12])
            for workers in ([2, 4] if args.matrix_v2 else [2])]
    random.Random(42).shuffle(jobs)
    rows = []
    for fault, seed, strategy, steps, workers in jobs:
        scenario = fixture(fault, seed, steps, workers)
        reduced, result = reduce_concurrent(scenario, lambda c: SimulatedDevice(c, fault), workers=workers, strategy=strategy)
        name = f"{fault}-{seed}-{strategy}"
        if args.matrix_v2:
            name += f"-{steps}ops-{workers}workers"
        save_json(args.output / f"{name}.json", {"input": scenario, "reduced": reduced, "result": result})
        rows.append({"fixture": fault, "seed": seed, "strategy": strategy, "steps": steps, "workers": workers,
                     **{key: result[key] for key in ("outcome", "attempts", "elapsed_ns",
                        "original_operations", "reduced_operations", "replay_success_rate", "total_trials",
                        "candidate_operations_executed", "total_operations_executed", "search_transitions")}})
    summary = []
    for fault, strategy, steps, workers in sorted({(r["fixture"], r["strategy"], r["steps"], r["workers"]) for r in rows}):
            group = [r for r in rows if (r["fixture"], r["strategy"], r["steps"], r["workers"]) == (fault, strategy, steps, workers)]
            summary.append({"fixture": fault, "strategy": strategy, "steps": steps, "workers": workers, "runs": len(group),
                            "outcomes": [r["outcome"] for r in group],
                            "reduced_sizes": [r["reduced_operations"] for r in group],
                            "median_candidate_checks": statistics.median(r["attempts"] for r in group),
                            "candidate_checks_range": [min(r["attempts"] for r in group), max(r["attempts"] for r in group)],
                            "median_elapsed_ms": statistics.median(r["elapsed_ns"] for r in group) / 1e6})
    save_json(args.output / "results.json", {"rows": rows, "summary": summary})
    manifest.update(status="complete", finished_utc=datetime.now(timezone.utc).isoformat(), runs=len(rows))
    save_json(args.output / "manifest.json", manifest)
    print(f"Saved {len(rows)} simulation experiments to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
