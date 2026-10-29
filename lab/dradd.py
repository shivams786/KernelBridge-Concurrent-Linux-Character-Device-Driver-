"""Bounded dependency-guided reduction with fixed-sample replay decisions.

Adapters own execution and classification. Dependencies constrain inclusion,
not scheduling. No inferred dataflow edge is treated as a causal fact.
"""

import copy
import math
import time

KINDS = {"HARD_STRUCTURAL", "CONTRACT_REQUIRED", "CONSERVATIVE_INFERRED", "OPTIONAL_HEURISTIC"}
REQUIRED = {"HARD_STRUCTURAL", "CONTRACT_REQUIRED"}
STRATEGIES = ("single", "chunk", "legacy", "dependency", "reproduction", "dradd")
STATES = {"SUCCESS_REPRODUCER", "HISTORY_ONLY_REDUCTION", "TARGET_FAILURE_NOT_REPRODUCED",
          "INVALID_CANDIDATE", "DIFFERENT_FAILURE", "INCOMPLETE_EXECUTION",
          "SEARCH_BUDGET_EXHAUSTED", "ENVIRONMENT_ERROR", "INCONCLUSIVE"}


def wilson(successes, valid, z=1.959963984540054):
    if (type(successes) is not int or type(valid) is not int or
            not 0 <= successes <= valid or not math.isfinite(z) or z <= 0):
        raise ValueError("invalid binomial counts or z")
    if not valid:
        return None
    p = successes / valid
    denominator = 1 + z * z / valid
    center = (p + z * z / (2 * valid)) / denominator
    radius = z * math.sqrt(p * (1 - p) / valid + z * z / (4 * valid * valid)) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


class Workload:
    """Immutable source plus stable original indexes; candidates never renumber edges."""

    def __init__(self, value):
        self.source = copy.deepcopy(value)
        ops = value.get("operations")
        owners = value.get("worker_ids")
        workers = value.get("workers")
        if (not isinstance(ops, list) or not 1 <= len(ops) <= 12 or
                type(workers) is not int or not 1 <= workers <= 4 or
                not isinstance(owners, list) or len(owners) != len(ops) or
                any(type(w) is not int or not 0 <= w < workers for w in owners)):
            raise ValueError("expected 1..12 operations and explicit valid worker ownership")
        self.ids = tuple(range(len(ops)))
        self.required = {i: set() for i in self.ids}
        edges = value.get("dependencies", [])
        if not isinstance(edges, list):
            raise ValueError("dependencies must be a list")
        seen = set()
        for edge in edges:
            if not isinstance(edge, dict) or set(edge) != {"operation", "requires", "kind"}:
                raise ValueError("invalid dependency record")
            a, b, kind = edge["operation"], edge["requires"], edge["kind"]
            if (type(a) is not int or type(b) is not int or a not in self.ids or b not in self.ids or
                    not isinstance(kind, str) or kind not in KINDS or a == b):
                raise ValueError("invalid dependency reference or kind")
            if (a, b, kind) in seen:
                raise ValueError("duplicate dependency")
            seen.add((a, b, kind))
            if kind in REQUIRED:
                self.required[a].add(b)
                if owners[a] == owners[b] and b > a:
                    raise ValueError("prerequisite conflicts with worker program order")
        # Check required edges plus program order, including cross-worker cycles.
        graph = {i: set(v) for i, v in self.required.items()}
        last = {}
        for i, owner in enumerate(owners):
            if owner in last:
                graph[i].add(last[owner])
            last[owner] = i
        visiting, done = set(), set()

        def visit(i):
            if i in visiting:
                raise ValueError("cyclic prerequisite/program-order constraints")
            if i in done:
                return
            visiting.add(i)
            for parent in graph[i]:
                visit(parent)
            visiting.remove(i)
            done.add(i)

        for i in self.ids:
            visit(i)

    def valid(self, keep):
        ids = set(keep)
        return (bool(keep) and tuple(sorted(ids)) == tuple(keep) and ids <= set(self.ids)
                and all(self.required[i] <= ids for i in keep))

    def prune(self, keep):
        """Delete dependents of missing prerequisites to a fixed point."""
        ids = set(keep)
        while True:
            next_ids = {i for i in ids if self.required[i] <= ids}
            if next_ids == ids:
                return tuple(sorted(ids))
            ids = next_ids

    def candidate(self, keep):
        if not self.valid(keep):
            raise ValueError("missing prerequisites or invalid candidate indexes")
        result = copy.deepcopy(self.source)
        result["operations"] = [copy.deepcopy(self.source["operations"][i]) for i in keep]
        result["worker_ids"] = [self.source["worker_ids"][i] for i in keep]
        result["original_ids"] = list(keep)
        mapping = {old: new for new, old in enumerate(keep)}
        result["dependencies"] = [dict(edge, operation=mapping[edge["operation"]],
                                        requires=mapping[edge["requires"]])
                                  for edge in self.source.get("dependencies", [])
                                  if edge["operation"] in mapping and edge["requires"] in mapping]
        return result


def trial_summary(trials, signature):
    counts = {key: 0 for key in ("target", "pass", "different", "timeout", "incomplete", "environment")}
    for trial in trials:
        status = trial.get("status")
        if status == "fail" and isinstance(trial.get("signature"), str):
            counts["target" if trial["signature"] == signature else "different"] += 1
        elif status == "pass":
            counts["pass"] += 1
        else:
            counts[status if status in ("timeout", "environment") else "incomplete"] += 1
    valid = counts["target"] + counts["pass"] + counts["different"]
    return {**counts, "valid": valid, "attempted": len(trials),
            "frequency": counts["target"] / valid if valid else None,
            "wilson95": wilson(counts["target"], valid)}


def accepted(stats, n, threshold, lower_bound):
    # Invalid attempts are never discarded to make acceptance easier.
    return (stats["valid"] == n and stats["target"] > 0 and
            stats["frequency"] >= threshold and
            (lower_bound is None or stats["wilson95"][0] >= lower_bound))


def rejection(stats):
    if stats["environment"]:
        return "ENVIRONMENT_ERROR"
    if stats["timeout"] or stats["incomplete"]:
        return "INCOMPLETE_EXECUTION"
    if stats["different"]:
        return "DIFFERENT_FAILURE"
    return "TARGET_FAILURE_NOT_REPRODUCED"


def reduce(workload, adapter, strategy="dradd", trials=5, max_executions=120,
           max_candidates=100, threshold=0.6, lower_bound=None, seed=42, checkpoint=None):
    """Fixed-budget deletion; no global-minimality or schedule-replay guarantee.

    adapter.validate(workload) raises ValueError for target-invalid inputs.
    adapter.execute(workload, trial_seed) returns status, signature, history and
    optional explored/operations_executed. Adapters must bound calls or run under
    an external watchdog. checkpoint receives JSON-safe progress, never code.
    """
    source = Workload(workload)
    adapter.validate(source.candidate(source.ids))
    if (strategy not in STRATEGIES or type(trials) is not int or not 1 <= trials <= 20 or
            type(max_executions) is not int or not 2 * trials <= max_executions <= 10000 or
            type(max_candidates) is not int or not 1 <= max_candidates <= 1000 or
            not math.isfinite(threshold) or not 0 < threshold <= 1 or
            (lower_bound is not None and (not math.isfinite(lower_bound) or not 0 <= lower_bound <= 1)) or
            type(seed) is not int):
        raise ValueError("invalid reduction policy/budget")
    signature = adapter.signature
    guided = strategy in ("dependency", "dradd")
    repeated = strategy in ("reproduction", "dradd")
    candidate_trials = 1 if strategy == "dependency" else trials
    decision_threshold = threshold if repeated else 1.0
    current = source.ids
    groups = []
    attempts = invalid = executions = 0
    exhausted = False
    start = time.perf_counter_ns()

    def replay(keep, phase, n, required_rate):
        nonlocal executions
        candidate = source.candidate(keep)
        raw = []
        for _ in range(n):
            # Seeds are independent of workload generation; paired strategies
            # share this stream, though differing search paths consume it differently.
            trial_seed = seed + executions
            began = time.perf_counter_ns()
            try:
                result = adapter.execute(copy.deepcopy(candidate), trial_seed)
                if not isinstance(result, dict):
                    raise ValueError("adapter result must be a dictionary")
            except Exception as exc:
                result = {"status": "environment", "error": f"{type(exc).__name__}: {exc}"}
            result = {**result, "trial_seed": trial_seed, "elapsed_ns": time.perf_counter_ns() - began}
            raw.append(result)
            executions += 1
        stats = trial_summary(raw, signature)
        ok = accepted(stats, n, required_rate, lower_bound if repeated else None)
        group = {"phase": phase, "ids": list(keep), "trials": raw, "statistics": stats,
                 "accepted": ok, "state": "SUCCESS_REPRODUCER" if ok else rejection(stats)}
        groups.append(group)
        if checkpoint:
            checkpoint({"phase": phase, "current_ids": list(current), "executions": executions,
                        "groups": groups})
        return ok, stats

    initial_ok, initial = replay(current, "initial", trials, threshold)
    confirmed = False
    final = initial
    if initial_ok:
        granularity = 2
        while len(current) > 1:
            size = len(current)
            width = 1 if strategy == "single" else math.ceil(size / granularity)
            changed = False
            for offset in range(0, size, width):
                if attempts >= max_candidates:
                    exhausted = True
                    break
                keep = current[:offset] + current[offset + width:]
                if guided:
                    keep = source.prune(keep)
                attempts += 1
                if not source.valid(keep):
                    invalid += 1
                    groups.append({"phase": "candidate", "ids": list(keep), "trials": [],
                                   "accepted": False, "state": "INVALID_CANDIDATE"})
                    continue
                try:
                    adapter.validate(source.candidate(keep))
                except ValueError as exc:
                    invalid += 1
                    groups.append({"phase": "candidate", "ids": list(keep), "trials": [],
                                   "accepted": False, "state": "INVALID_CANDIDATE", "error": str(exc)})
                    continue
                if executions + candidate_trials + trials > max_executions:
                    exhausted = True
                    break
                ok, _ = replay(keep, "candidate", candidate_trials, decision_threshold)
                if ok:
                    current = keep
                    granularity = max(2, granularity - 1)
                    changed = True
                    break
            if exhausted:
                break
            if not changed:
                if strategy == "single" or granularity >= size:
                    break
                granularity = min(size, granularity * 2)
        # Independent final group is reserved, even when search exhausts its budget.
        confirmed, final = replay(current, "confirmation", trials, threshold)
    outcome = ("SUCCESS_REPRODUCER" if confirmed else rejection(final))
    result = {"schema_version": 1, "strategy": strategy, "outcome": outcome,
              "search_state": "SEARCH_BUDGET_EXHAUSTED" if exhausted else "FINISHED",
              "signature": signature, "signature_scope": "observable symptom, not root cause",
              "original_operations": len(source.ids), "reduced_operations": len(current),
              "reduced": source.candidate(current), "confirmed": confirmed,
              "strictly_reduced": len(current) < len(source.ids), "statistics": final,
              "candidate_evaluations": attempts, "invalid_candidates": invalid,
              "actual_executions": executions,
              "candidate_executions": sum(len(g["trials"]) for g in groups if g["phase"] == "candidate"),
              "operations_executed": sum(t.get("operations_executed", len(t.get("history", [])))
                                         for g in groups for t in g["trials"]),
              "search_transitions": sum(t.get("explored", 0) for g in groups for t in g["trials"]),
              "replay_ns": sum(t["elapsed_ns"] for g in groups for t in g["trials"]),
              "elapsed_ns": time.perf_counter_ns() - start,
              "policy": {"trials": trials, "candidate_trials": candidate_trials, "threshold": decision_threshold,
                         "confirmation_threshold": threshold,
                         "lower_bound": lower_bound if repeated else None, "max_executions": max_executions,
                         "max_candidates": max_candidates, "algorithm_seed": seed},
              "adapter": adapter.metadata(), "groups": groups}
    return result
