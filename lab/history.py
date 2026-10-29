"""Bounded linearizability checking for complete nonblocking FIFO histories."""

import argparse
import copy
import json
from pathlib import Path

from .contract import ReferenceModel, validate

MAX_HISTORY = 12


def reduce_history_prefix(capacity, history, budget=10000):
    """Trim only at quiescent cuts; never delete a possible overlapping producer.

    This is recorded evidence, not execution. Restricting removal to suffixes
    preserves every prior state transition and all within-worker dependencies.
    """
    original = check_history(capacity, history, len(history), budget)
    if original["status"] != "fail":
        return {"classification": "INCONCLUSIVE" if original["status"] == "inconclusive" else "NO_COUNTEREXAMPLE",
                "result": original, "history": copy.deepcopy(history), "checks": 1}
    ordered = sorted(history, key=lambda e: (e["started_ns"], e["worker"], e["sequence"]))
    checks = 1
    for size in range(1, len(ordered) + 1):
        if size < len(ordered) and max(e["finished_ns"] for e in ordered[:size]) >= ordered[size]["started_ns"]:
            continue
        candidate = copy.deepcopy(ordered[:size])
        for index, event in enumerate(candidate):
            event["original_index"] = event["index"]
            event["index"] = index
        result = check_history(capacity, candidate, size, budget)
        checks += 1
        if result["status"] == "fail":
            return {"classification": "HISTORY_COUNTEREXAMPLE", "executed": False,
                    "strategy": "quiescent-prefix", "history": candidate, "result": result,
                    "checks": checks, "original_operations": len(history), "reduced_operations": size}
    return {"classification": "INCONCLUSIVE", "history": copy.deepcopy(history), "checks": checks}


def check_history(capacity, history, expected_count, budget=10000):
    """Find a legal sequential explanation consistent with observed real time.

    Equal timestamps are conservatively treated as overlapping. Worker sequence
    numbers provide program order even on clocks with coarse resolution.
    """
    if type(budget) is not int or not 1 <= budget <= 100000:
        raise ValueError("search budget must be 1..100000")
    if type(expected_count) is not int or not 1 <= expected_count <= MAX_HISTORY:
        raise ValueError("expected count must be 1..12")
    if not isinstance(history, list) or len(history) != expected_count:
        return {"status": "inconclusive", "reason": "incomplete history", "explored": 0}
    indexes = set()
    worker_sequences = set()
    for event in history:
        if not isinstance(event, dict):
            raise ValueError("history events must be objects")
        for field in ("index", "worker", "sequence", "started_ns", "finished_ns"):
            if type(event.get(field)) is not int or event[field] < 0:
                raise ValueError(f"invalid {field}")
        if event["finished_ns"] < event["started_ns"]:
            raise ValueError("operation completes before invocation")
        if event["index"] in indexes:
            raise ValueError("duplicate operation index")
        indexes.add(event["index"])
        sequence = (event["worker"], event["sequence"])
        if sequence in worker_sequences:
            raise ValueError("duplicate worker sequence")
        worker_sequences.add(sequence)
        if "operation" not in event:
            raise ValueError("missing operation")
        if "error" in event or "actual" not in event:
            return {"status": "inconclusive", "reason": "worker did not complete normally", "explored": 0}
        actual = event["actual"]
        if not isinstance(actual, dict) or type(actual.get("ret")) is not int or type(actual.get("errno")) is not int:
            raise ValueError("malformed result")
    if indexes != set(range(expected_count)):
        raise ValueError("operation indexes must cover 0..expected_count-1")
    for worker in {event["worker"] for event in history}:
        sequences = sorted(event["sequence"] for event in history if event["worker"] == worker)
        if sequences != list(range(len(sequences))):
            raise ValueError("worker sequences must start at zero without gaps")
    validate({"version": 1, "capacity": capacity,
              "operations": [event["operation"] for event in history]})
    predecessors = [0] * len(history)
    for i, event in enumerate(history):
        for j, other in enumerate(history):
            if i == j:
                continue
            same_worker_before = (event["worker"] == other["worker"] and
                                  other["sequence"] < event["sequence"])
            if same_worker_before and other["finished_ns"] > event["started_ns"]:
                raise ValueError("overlapping or reversed calls within one worker")
            if other["finished_ns"] < event["started_ns"] or same_worker_before:
                predecessors[i] |= 1 << j

    explored = 0
    complete = (1 << len(history)) - 1

    class BudgetExhausted(Exception):
        pass

    def search(mask, model, order):
        nonlocal explored
        if mask == complete:
            return order
        for i, event in enumerate(history):
            bit = 1 << i
            if mask & bit or predecessors[i] & ~mask:
                continue
            if explored >= budget:
                raise BudgetExhausted
            explored += 1
            candidate = ReferenceModel(model.capacity)
            candidate.data = model.data.copy()
            if candidate.apply(event["operation"]) != event["actual"]:
                continue
            found = search(mask | bit, candidate, order + [event["index"]])
            if found is not None:
                return found
        return None

    try:
        witness = search(0, ReferenceModel(capacity), [])
    except BudgetExhausted:
        return {"status": "inconclusive", "reason": "search budget exhausted", "explored": explored}
    if witness is not None:
        return {"status": "pass", "witness_order": witness, "explored": explored}
    return {"status": "fail", "reason": "no legal FIFO ordering", "explored": explored}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="completed concurrent run directory")
    parser.add_argument("--budget", type=int, default=10000)
    args = parser.parse_args(argv)
    try:
        scenario = json.loads((args.directory / "scenario.json").read_text(encoding="utf-8"))
        manifest = json.loads((args.directory / "manifest.json").read_text(encoding="utf-8"))
        result_path = args.directory / "result.json"
        execution = (json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists()
                     else {"error": "missing execution result"})
        if not isinstance(manifest, dict) or not isinstance(execution, dict):
            raise ValueError("manifest and execution result must be objects")
        if manifest.get("scope") != "bounded concurrent nonblocking byte-stream contract":
            raise ValueError("not a concurrent run")
        validate(scenario)
        if (manifest.get("status") not in ("pass", "fail", "inconclusive") or
                execution.get("error") or
                execution.get("status") != manifest.get("status") or
                (execution.get("status") == "inconclusive" and
                 execution.get("reason") != "search budget exhausted") or
                manifest.get("operations_observed") != len(scenario["operations"])):
            result = {"status": "inconclusive", "reason": "run did not finish conclusively"}
        else:
            workers = manifest.get("workers")
            if type(workers) is not int or not 2 <= workers <= 4:
                raise ValueError("saved worker count must be 2..4")
            assignments = scenario.get("worker_ids", [i % workers for i in range(len(scenario["operations"]))])
            if (not isinstance(assignments, list) or len(assignments) != len(scenario["operations"]) or
                    any(type(worker) is not int or not 0 <= worker < workers for worker in assignments)):
                raise ValueError("invalid saved worker assignment")
            history = [json.loads(line) for line in
                       (args.directory / "history.jsonl").read_text(encoding="utf-8").splitlines()]
            for event in history:
                if not isinstance(event, dict):
                    raise ValueError("history events must be objects")
                index = event.get("index")
                if (type(index) is not int or not 0 <= index < len(scenario["operations"]) or
                        event.get("operation") != scenario["operations"][index]):
                    raise ValueError("history does not match saved scenario")
                owner = assignments[index]
                if (event.get("worker") != owner or
                        event.get("sequence") != assignments[:index].count(owner)):
                    raise ValueError("history does not match saved worker program order")
            result = check_history(scenario["capacity"], history, len(scenario["operations"]), args.budget)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return {"pass": 0, "fail": 1, "inconclusive": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
