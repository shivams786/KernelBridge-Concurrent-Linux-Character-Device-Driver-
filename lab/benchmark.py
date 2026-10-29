"""Reproducible single-process write/read round-trip measurements."""

import argparse
import csv
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import platform
import random
import socket
import statistics
import subprocess
import sys
import time

from .backends import LinuxDevice
from .runner import ROOT, git_output, save_json


class Transport:
    def __init__(self, backend, capacity=4096, path="/dev/ringbuf_char", abi_program=None):
        self.backend = backend
        self.capacity = capacity
        self.path = path
        self.abi_program = abi_program or ROOT / "userspace" / "abi_dump"
        self.resources = []
        self.device = None

    def __enter__(self):
        try:
            if self.backend == "pipe":
                reader, writer = os.pipe()
                self.resources = [lambda: os.close(reader), lambda: os.close(writer)]
                os.set_blocking(reader, False)
                os.set_blocking(writer, False)
                self.send = lambda data: os.write(writer, data)
                self.receive = lambda count: os.read(reader, count)
                self.description = "anonymous pipe, nonblocking descriptors"
            elif self.backend == "socketpair":
                # Bound the Windows loopback fallback's accept; restore the
                # process default before performing any measurements.
                previous_timeout = socket.getdefaulttimeout()
                try:
                    socket.setdefaulttimeout(2.0)
                    writer, reader = socket.socketpair()
                finally:
                    socket.setdefaulttimeout(previous_timeout)
                self.resources = [reader.close, writer.close]
                writer.setblocking(False)
                reader.setblocking(False)
                self.send, self.receive = writer.send, reader.recv
                self.description = f"socketpair, family={writer.family.name}, nonblocking sockets"
            elif self.backend == "device":
                self.device = LinuxDevice(self.capacity, self.path, self.abi_program)
                self.device.__enter__()
                self.send = lambda data: os.write(self.device.fd, data)
                self.receive = lambda count: os.read(self.device.fd, count)
                self.description = f"ringbuf_char, O_NONBLOCK, capacity={self.capacity}"
            else:
                raise ValueError("unknown backend")
        except BaseException as original:
            try:
                self._close_resources()
            except Exception as cleanup:
                raise original from cleanup
            raise
        return self

    def _close_resources(self):
        resources, self.resources = self.resources, []
        # ExitStack attempts every callback even when one close fails.
        with ExitStack() as stack:
            for close in reversed(resources):
                stack.callback(close)

    def __exit__(self, exc_type, exc_value, traceback):
        if self.device is not None:
            return self.device.__exit__(exc_type, exc_value, traceback)
        try:
            self._close_resources()
        except Exception as cleanup:
            if exc_value is not None:
                raise exc_value.with_traceback(traceback) from cleanup
            raise
        return False


def exchange(transport, payload):
    """Short transfers are completed; EAGAIN/EOF abort instead of spinning."""
    offset = 0
    write_calls = 0
    read_calls = 0
    short_writes = 0
    short_reads = 0
    view = memoryview(payload)
    while offset < len(payload):
        count = transport.send(view[offset:])
        if not 0 < count <= len(payload) - offset:
            raise RuntimeError("write made no progress or returned an invalid count")
        short_writes += count < len(payload) - offset
        offset += count
        write_calls += 1
    chunks = []
    remaining = len(payload)
    while remaining:
        data = transport.receive(remaining)
        if not data or len(data) > remaining:
            raise RuntimeError("unexpected EOF or invalid read length")
        short_reads += len(data) < remaining
        remaining -= len(data)
        chunks.append(data)
        read_calls += 1
    return b"".join(chunks), (write_calls, read_calls, short_writes, short_reads)


def percentile(sorted_values, percent):
    if not sorted_values or not 0 < percent <= 100:
        raise ValueError("percentile requires nonempty values and 0 < percent <= 100")
    return sorted_values[math.ceil(len(sorted_values) * percent / 100) - 1]


def summarize(samples, size, wall_ns, cpu_ns):
    if not samples or wall_ns <= 0 or cpu_ns < 0:
        raise ValueError("invalid measurement interval")
    ordered = sorted(samples)
    return {"iterations": len(samples), "payload_bytes": size,
            "round_trip_ns": {"min": ordered[0], "p50": percentile(ordered, 50),
                              "p95": percentile(ordered, 95), "p99": percentile(ordered, 99),
                              "max": ordered[-1], "mean": statistics.mean(ordered)},
            "round_trip_stdev_ns": statistics.pstdev(ordered),
            "process_cpu_percent": 100 * cpu_ns / wall_ns,
            "wall_ns": wall_ns, "process_cpu_ns": cpu_ns,
            "logical_mib_s": size * len(samples) * 1e9 / wall_ns / (1024 * 1024),
            "round_trips_s": len(samples) * 1e9 / wall_ns}


def usage():
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF)
        return {"voluntary_context_switches": value.ru_nvcsw,
                "involuntary_context_switches": value.ru_nivcsw,
                "peak_process_rss": value.ru_maxrss,
                "peak_process_rss_unit": "bytes" if sys.platform == "darwin" else "KiB"}
    except ImportError:
        return None


def measure(transport, size, iterations, warmup):
    # Vary contents outside each timed exchange to detect stale returned payloads.
    def payload_for(index):
        marker = index.to_bytes(8, "little")
        return (marker * ((size + 7) // 8))[:size]

    for index in range(warmup):
        payload = payload_for(index)
        data, _ = exchange(transport, payload)
        if data != payload:
            raise RuntimeError("warmup payload mismatch")
    samples = []
    counters = [0, 0, 0, 0]
    before = usage()
    cpu_start = time.process_time_ns()
    wall_start = time.perf_counter_ns()
    for index in range(iterations):
        payload = payload_for(index + warmup)
        started = time.perf_counter_ns()
        data, counts = exchange(transport, payload)
        elapsed = time.perf_counter_ns() - started
        if data != payload:
            raise RuntimeError("measured payload mismatch")
        samples.append(elapsed)
        for field, count in enumerate(counts):
            counters[field] += count
    wall_ns = time.perf_counter_ns() - wall_start
    cpu_ns = time.process_time_ns() - cpu_start
    after = usage()
    result = summarize(samples, size, wall_ns, cpu_ns)
    result.update(zip(("write_calls", "read_calls", "short_writes", "short_reads"), counters))
    result["resource_usage"] = None if before is None else {
        "voluntary_context_switches": after["voluntary_context_switches"] - before["voluntary_context_switches"],
        "involuntary_context_switches": after["involuntary_context_switches"] - before["involuntary_context_switches"],
        "peak_process_rss": after["peak_process_rss"],
        "peak_process_rss_unit": after["peak_process_rss_unit"]}
    return result, samples


def aggregate(runs):
    groups = {}
    for run in runs:
        key = (run["backend"], run["size"])
        groups.setdefault(key, []).append(run)
    rows = []
    for (backend, size), attempts in sorted(groups.items()):
        complete = [run for run in attempts if run["status"] == "complete"]
        row = {"backend": backend, "size": size, "completed_repeats": len(complete),
               "attempted_repeats": len(attempts)}
        if complete:
            rates = [run["measurement"]["logical_mib_s"] for run in complete]
            row.update(logical_mib_s_median=statistics.median(rates),
                       logical_mib_s_min=min(rates), logical_mib_s_max=max(rates),
                       per_repeat_p99_ns_median=statistics.median(
                           run["measurement"]["round_trip_ns"]["p99"] for run in complete))
        rows.append(row)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backends", nargs="+", choices=["pipe", "socketpair", "device"], default=["pipe", "socketpair"])
    parser.add_argument("--sizes", nargs="+", type=int, default=[1, 64, 256])
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--warmup", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--capacity", type=int, default=4096)
    parser.add_argument("--device", default="/dev/ringbuf_char")
    parser.add_argument("--abi-program", type=Path, default=ROOT / "userspace" / "abi_dump")
    parser.add_argument("--exclusive", action="store_true", help="acknowledge device buffer destruction and exclusive use")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if (not 1 <= args.iterations <= 100000 or not 0 <= args.warmup <= 10000 or
            not 1 <= args.repeats <= 20 or not 256 <= args.capacity <= 65536 or
            any(not 1 <= size <= min(4096, args.capacity) for size in args.sizes)):
        parser.error("invalid bounds: iterations 1..100000, warmup 0..10000, repeats 1..20, capacity 256..65536, sizes 1..min(4096,capacity)")
    if len(set(args.backends)) != len(args.backends) or len(set(args.sizes)) != len(args.sizes):
        parser.error("duplicate backends or sizes")
    if len(args.sizes) > 8:
        parser.error("at most eight payload sizes per invocation")
    if "device" in args.backends and not args.exclusive:
        parser.error("device benchmarking requires --exclusive")
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(str(exc))
    jobs = [{"backend": backend, "size": size, "repeat": repeat}
            for repeat in range(args.repeats) for size in args.sizes for backend in args.backends]
    random.Random(args.seed).shuffle(jobs)
    manifest = {"schema_version": 1, "kind": "round-trip-benchmark", "status": "running",
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "platform": platform.platform(), "processor": platform.processor(), "python": sys.version,
                "cpu_count": os.cpu_count(), "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
                "clock": "perf_counter", "clock_resolution_seconds": time.get_clock_info("perf_counter").resolution,
                "git_commit": git_output("rev-parse", "HEAD"), "git_status": git_output("status", "--porcelain"),
                "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted((ROOT / "lab").glob("*.py"))},
                "settings": {"iterations": args.iterations, "warmup": args.warmup, "repeats": args.repeats,
                             "seed": args.seed, "capacity": args.capacity, "device": args.device if "device" in args.backends else None},
                "job_order": jobs, "scope": "single-process Python write/read round trips; not saturation throughput"}
    save_json(args.output / "manifest.json", manifest)
    runs = []
    with (args.output / "samples.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["run", "backend", "size", "repeat", "sample", "round_trip_ns"])
        for number, job in enumerate(jobs):
            run = {"run": number, **job}
            try:
                with Transport(job["backend"], args.capacity, args.device, args.abi_program) as transport:
                    run["transport"] = transport.description
                    measurement, samples = measure(transport, job["size"], args.iterations, args.warmup)
                run.update(status="complete", measurement=measurement)
                for index, elapsed in enumerate(samples):
                    writer.writerow([number, job["backend"], job["size"], job["repeat"], index, elapsed])
                stream.flush()
            except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                run.update(status="inconclusive", error=f"{type(exc).__name__}: {exc}", errno=getattr(exc, "errno", None))
            runs.append(run)
            save_json(args.output / f"run-{number:03d}.json", run)
            print(f"{run['status'].upper()}: {job['backend']} {job['size']} bytes, repeat {job['repeat']}")
    summary = aggregate(runs)
    save_json(args.output / "summary.json", summary)
    manifest.update(status="complete" if all(run["status"] == "complete" for run in runs) else "incomplete",
                    finished_utc=datetime.now(timezone.utc).isoformat())
    save_json(args.output / "manifest.json", manifest)
    print(f"Evidence: {args.output}")
    return 0 if manifest["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
