"""Collect bounded overlapping calls without serializing real device access."""

from concurrent.futures import ThreadPoolExecutor
import random
import threading
import time

from .contract import validate
from .history import MAX_HISTORY, check_history


def validate_worker_plan(scenario, workers):
    """Validate ownership before a runner creates evidence or opens a device."""
    validate(scenario)
    operations = scenario["operations"]
    if type(workers) is not int or not 2 <= workers <= 4 or not 1 <= len(operations) <= MAX_HISTORY:
        raise ValueError("concurrent runs require 2..4 workers and 1..12 operations")
    assignments = scenario.get("worker_ids", [i % workers for i in range(len(operations))])
    if (not isinstance(assignments, list) or len(assignments) != len(operations) or
            any(type(w) is not int or not 0 <= w < workers for w in assignments)):
        raise ValueError("worker_ids must assign every operation to an existing worker")
    return assignments


def evaluate_concurrent(scenario, factory, workers, budget=10000, record=None):
    assignments = validate_worker_plan(scenario, workers)
    operations = scenario["operations"]
    jitter = scenario.get("jitter_us", 0)
    if type(jitter) is not int or not 0 <= jitter <= 10000:
        raise ValueError("jitter_us must be 0..10000")
    if not 1 <= budget <= 100000:
        raise ValueError("search budget must be 1..100000")
    history = []
    history_lock = threading.Lock()
    barrier = threading.Barrier(workers, timeout=5)
    try:
        with factory(scenario["capacity"]) as device:
            def worker(worker_id):
                barrier.wait()
                rng = random.Random(f"{scenario.get('seed', 0)}:{worker_id}")
                indexes = [i for i, owner in enumerate(assignments) if owner == worker_id]
                for sequence, index in enumerate(indexes):
                    if jitter:
                        time.sleep(rng.randrange(jitter + 1) / 1e6)
                    event = {"index": index, "worker": worker_id, "sequence": sequence,
                             "operation": operations[index], "started_ns": time.perf_counter_ns()}
                    try:
                        event["actual"] = device.apply(operations[index])
                    except Exception as exc:
                        event["error"] = f"{type(exc).__name__}: {exc}"
                    event["finished_ns"] = time.perf_counter_ns()
                    # Only evidence writes are serialized, after the syscall completes.
                    with history_lock:
                        history.append(event)
                        if record is not None:
                            record(event)
                    if "error" in event:
                        break

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(worker, worker_id) for worker_id in range(workers)]
                for future in futures:
                    future.result()
    except Exception as exc:
        return {"status": "inconclusive", "history": history, "failure_class": "EXECUTION_ERROR",
                "error": f"{type(exc).__name__}: {exc}"}
    try:
        result = check_history(scenario["capacity"], history, len(operations), budget)
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "inconclusive", "history": history, "failure_class": "INVALID_CAPTURE",
                "error": f"{type(exc).__name__}: {exc}"}
    result["history"] = history
    return result
