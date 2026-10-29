"""Experimental simulation-only concurrent workload reduction with fresh replays."""

import argparse
import json
from pathlib import Path
import platform
import time

from .backends import SimulatedDevice
from .concurrency import evaluate_concurrent
from .contract import validate
from .runner import ROOT, git_output, save_json
from .validate_linux import snapshot


SIGNATURE = "NO_LEGAL_FIFO_ORDERING"


def reduce_concurrent(scenario, factory, workers=2, strategy="chunk", trials=3,
                      budget=100, search_budget=10000, evaluator=evaluate_concurrent):
    """Accept a deletion only when every fresh trial fails the same contract.

    The signature is a contract-failure class, not a root-cause identity. Worker
    ownership and per-worker order survive deletion; observed timestamps do not.
    Budget counts candidate groups, excluding initial and final confirmation.
    """
    validate(scenario)
    if (type(workers) is not int or not 2 <= workers <= 4 or
            not 1 <= len(scenario["operations"]) <= 12):
        raise ValueError("expected 2..4 workers and 1..12 operations")
    if (strategy not in ("single", "chunk") or type(trials) is not int or
            not 1 <= trials <= 20 or type(budget) is not int or not 1 <= budget <= 100):
        raise ValueError("invalid strategy, trials (1..20), or candidate budget (1..100)")
    owners = scenario.get("worker_ids", [i % workers for i in range(len(scenario["operations"]))])
    if (not isinstance(owners, list) or len(owners) != len(scenario["operations"]) or
            any(type(w) is not int or not 0 <= w < workers for w in owners)):
        raise ValueError("invalid worker_ids")
    if type(search_budget) is not int or not 1 <= search_budget <= 100000:
        raise ValueError("search budget must be 1..100000")
    current = {**scenario, "worker_ids": owners.copy()}
    evidence = []
    started = time.perf_counter_ns()

    def replay(candidate, phase):
        results = [evaluator(candidate, factory, workers, search_budget) for _ in range(trials)]
        counts = {status: sum(r["status"] == status for r in results)
                  for status in ("pass", "fail", "inconclusive")}
        matched = sum(r["status"] == "fail" and r.get("reason") == "no legal FIFO ordering"
                      for r in results)
        evidence.append({"phase": phase, "scenario": candidate, "counts": counts,
                         "matched_failures": matched, "trials": results})
        return matched == trials, counts

    reproduced, initial_counts = replay(current, "initial")
    attempts = 0
    granularity = 2
    if reproduced:
        while len(current["operations"]) > 1 and attempts < budget:
            size = len(current["operations"])
            chunk = 1 if strategy == "single" else (size + granularity - 1) // granularity
            changed = False
            for start in range(0, size, chunk):
                keep = [i for i in range(size) if not start <= i < start + chunk]
                if not keep:
                    continue
                candidate = {**current, "operations": [current["operations"][i] for i in keep],
                             "worker_ids": [current["worker_ids"][i] for i in keep]}
                attempts += 1
                accepted, _ = replay(candidate, "candidate")
                if accepted:
                    current = candidate
                    granularity = max(2, granularity - 1)
                    changed = True
                    break
                if attempts >= budget:
                    break
            if not changed:
                if strategy == "single" or granularity >= size:
                    break
                granularity = min(size, granularity * 2)
        confirmed, counts = replay(current, "confirmation")
    else:
        confirmed, counts = False, initial_counts
    outcome = ("EXECUTABLE_REPRODUCER_FOUND" if confirmed else
               "INCONCLUSIVE" if counts["inconclusive"] else "REPRODUCTION_FAILED")
    summary = {"schema_version": 1, "evidence_kind": "SIMULATION", "kernel_validated": False,
               "outcome": outcome, "signature": SIGNATURE, "signature_scope": "contract class, not root cause",
               "strategy": strategy, "workers": workers, "attempts": attempts, "budget": budget,
               "trials_per_candidate": trials, "search_budget": search_budget,
               "original_operations": len(scenario["operations"]),
               "reduced_operations": len(current["operations"]), "confirmed": confirmed,
               "confirmation_counts": counts,
               "replay_success_rate": evidence[-1]["matched_failures"] / trials,
               "total_trials": sum(len(group["trials"]) for group in evidence),
               "candidate_operations_executed": sum(len(r.get("history", [])) for group in evidence
                                                     if group["phase"] == "candidate" for r in group["trials"]),
               "total_operations_executed": sum(len(r.get("history", [])) for group in evidence for r in group["trials"]),
               "search_transitions": sum(r.get("explored", 0) for group in evidence for r in group["trials"]),
               "schedule_control": "CONTROLLED_START",
               "replay_mode": "REPEATED_SCHEDULE_ATTEMPT",
               "observed_reproduction": confirmed,
               "elapsed_ns": time.perf_counter_ns() - started,
               "candidate_evidence": evidence}
    return current, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--fault", choices=["none", "false-eof", "reverse-read", "resize-loss"], default="none")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--strategy", choices=["single", "chunk"], default="chunk")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--budget", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
        validate(scenario)
        args.output.mkdir(parents=True, exist_ok=False)
        save_json(args.output / "scenario.json", scenario)
        sources = snapshot(ROOT, args.output / "source",
                           [p.relative_to(ROOT).as_posix() for p in (ROOT / "lab").glob("*.py")])
        save_json(args.output / "manifest.json", {"status": "running", "backend": "simulated",
                  "kernel_validated": False, "git_commit": git_output("rev-parse", "HEAD"),
                  "git_status": git_output("status", "--porcelain"), "fixture_fault": args.fault,
                  "platform": platform.platform(),
                  "source_snapshot": "source",
                  "source_sha256": {name: record["working_sha256"] for name, record in sources.items()}})
        reduced, result = reduce_concurrent(scenario, lambda c: SimulatedDevice(c, args.fault),
                                           args.workers, args.strategy, args.trials, args.budget)
        save_json(args.output / "reduced.json", reduced)
        save_json(args.output / "reduction.json", result)
        manifest = json.loads((args.output / "manifest.json").read_text())
        manifest["status"] = result["outcome"]
        save_json(args.output / "manifest.json", manifest)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"{result['outcome']}: {result['original_operations']} -> {result['reduced_operations']} operations")
    return {"EXECUTABLE_REPRODUCER_FOUND": 0, "REPRODUCTION_FAILED": 1, "INCONCLUSIVE": 2}[result["outcome"]]


if __name__ == "__main__":
    raise SystemExit(main())
