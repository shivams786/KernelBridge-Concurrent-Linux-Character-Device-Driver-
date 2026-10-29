"""Run, verify, and report bounded paired DRADD studies (standard library only)."""

import argparse
import hashlib
import html
import itertools
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys

from .dradd import Workload, reduce, trial_summary
from .research_targets import FAULTS, FIFOAdapter, RegisterAdapter, fixture
from .runner import ROOT, git_output, save_json
from .validate_linux import run_step, snapshot

METHODS = ["single", "chunk", "dependency", "reproduction", "dradd"]
CONFIGS = {
    "smoke": {"faults": ["none", "false-eof", "intermittent-eof"], "seeds": [11],
              "workers": [2], "lengths": [6], "densities": ["none", "sparse"]},
    "full": {"faults": list(FAULTS), "seeds": [11, 29], "workers": [2, 4],
             "lengths": [6, 10], "densities": ["none", "dense"]},
    "sensitivity": {"faults": ["intermittent-eof"], "seeds": [11, 29, 47], "workers": [2],
                    "lengths": [8], "densities": ["none", "dense"], "thresholds": [0.4, 0.8]},
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(directory):
    files = {p.relative_to(directory).as_posix(): digest(p) for p in sorted(directory.rglob("*"))
             if p.is_file() and p.name != "integrity.json" and "__pycache__" not in p.parts}
    save_json(directory / "integrity.json", {"schema_version": 1, "sha256": files})


def verify(directory):
    directory = directory.resolve()
    index = json.loads((directory / "integrity.json").read_text(encoding="utf-8"))
    if index.get("schema_version") != 1 or not isinstance(index.get("sha256"), dict):
        raise ValueError("invalid integrity index")
    files = index["sha256"]
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*")
              if p.is_file() and p.name != "integrity.json" and "__pycache__" not in p.parts}
    if actual != set(files):
        raise ValueError("bundle file inventory differs")
    for name, expected in files.items():
        relative = Path(name)
        path = directory / relative
        if (relative.is_absolute() or ".." in relative.parts or path.is_symlink() or
                not path.resolve().is_relative_to(directory) or digest(path) != expected):
            raise ValueError(f"bundle hash/path mismatch: {name}")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != "DRADD_STUDY" or manifest.get("status") != "complete":
        raise ValueError("incomplete or unsupported study")
    for job in manifest["jobs"]:
        path = directory / job["result"]
        if job["result"] not in files:
            raise ValueError("missing result")
        result = json.loads(path.read_text(encoding="utf-8"))
        request = json.loads((directory / job["request"]).read_text(encoding="utf-8"))
        source = Workload(request["workload"])
        ids = tuple(result["reduced"]["original_ids"])
        if source.candidate(ids) != result["reduced"]:
            raise ValueError("reduced workload differs from source projection")
        executions = 0
        for group in result["groups"]:
            if group["state"] == "INVALID_CANDIDATE":
                if group["trials"]:
                    raise ValueError("invalid candidate executed")
                continue
            if not source.valid(tuple(group["ids"])):
                raise ValueError("executed invalid dependencies")
            if trial_summary(group["trials"], result["signature"]) != group["statistics"]:
                raise ValueError("inconsistent trial statistics")
            executions += len(group["trials"])
        if executions != result["actual_executions"] or executions > result["policy"]["max_executions"]:
            raise ValueError("inconsistent execution budget")
        if result["statistics"] != result["groups"][-1]["statistics"]:
            raise ValueError("final statistics mismatch")
        if result["confirmed"] and result["groups"][-1]["phase"] != "confirmation":
            raise ValueError("unconfirmed success")
        if trial_summary(result["holdout"], result["signature"]) != result["holdout_statistics"]:
            raise ValueError("holdout statistics mismatch")
    return {"status": "verified", "files": len(files), "jobs": len(manifest["jobs"]),
            "scope": "integrity and structural/statistical consistency, not authenticity or new execution"}


def execute_job(request, output):
    config = request["config"]
    adapter = RegisterAdapter() if request.get("target") == "register" else FIFOAdapter(
        config["fault"], probability=config.get("probability", 0.7), delay_us=config.get("delay_us", 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    result = reduce(request["workload"], adapter, request["strategy"], trials=config["trials"],
                    max_executions=config["max_executions"], max_candidates=config["max_candidates"],
                    threshold=config["threshold"], seed=config["algorithm_seed"],
                    checkpoint=lambda data: save_json(output.with_suffix(".checkpoint.json"), data))
    # Fixed independent seed range, never used for candidate acceptance.
    holdout = [adapter.execute(result["reduced"], config["algorithm_seed"] + 1000000 + i)
               for i in range(config["holdout_trials"])]
    result.update(holdout=holdout, holdout_statistics=trial_summary(holdout, adapter.signature),
                  case=request["case"], config=config)
    save_json(output, result)
    return result


def distribution(values):
    if not values:
        return None
    ordered = sorted(values)
    return {"n": len(values), "mean": statistics.mean(values), "median": statistics.median(values),
            "p10": ordered[math.ceil(len(values) * 0.1) - 1],
            "p90": ordered[math.ceil(len(values) * 0.9) - 1], "min": ordered[0], "max": ordered[-1]}


def analyze(results):
    methods = {}
    metrics = ["reduced_operations", "candidate_evaluations", "actual_executions", "candidate_executions",
               "invalid_candidates", "operations_executed", "search_transitions", "elapsed_ns", "replay_ns"]
    for strategy in METHODS:
        rows = [r for r in results if r["strategy"] == strategy]
        methods[strategy] = {"runs": len(rows), "confirmed": sum(r["confirmed"] for r in rows),
                             "strictly_reduced_confirmed": sum(r["confirmed"] and r["strictly_reduced"] for r in rows),
                             "budget_exhausted": sum(r["search_state"] == "SEARCH_BUDGET_EXHAUSTED" for r in rows),
                             "metrics": {key: distribution([r[key] for r in rows]) for key in metrics},
                             "holdout_frequency": distribution([r["holdout_statistics"]["frequency"] for r in rows
                                                                 if r["holdout_statistics"]["frequency"] is not None]),
                             "outcomes": {key: sum(r["outcome"] == key for r in rows)
                                          for key in sorted({r["outcome"] for r in rows})}}
    pairs = []
    by_case = {}
    for row in results:
        by_case.setdefault(row["case"], {})[row["strategy"]] = row
    for baseline in METHODS[:-1]:
        both = [(rows[baseline], rows["dradd"]) for rows in by_case.values()
                if baseline in rows and "dradd" in rows]
        effects = {}
        for metric in metrics:
            selected = [(a, b) for a, b in both if metric != "reduced_operations" or
                        (a["confirmed"] and b["confirmed"])]
            delta = [b[metric] - a[metric] for a, b in selected]
            effects[metric] = {"dradd_minus_baseline": distribution(delta),
                               "dradd_lower": sum(d < 0 for d in delta), "equal": sum(d == 0 for d in delta),
                               "dradd_higher": sum(d > 0 for d in delta)}
        pairs.append({"baseline": baseline, "pairs": len(both), "effects": effects})
    return {"methods": methods, "paired": pairs,
            "interpretation": "descriptive paired effects, not independent samples or significance tests; size uses jointly confirmed pairs",
            "legacy": "candidate policy equivalent to chunk; common initial/final policy differs from historical CLI"}


def report(directory, results, analysis):
    rows = []
    for result in results:
        stats = result["holdout_statistics"]
        freq = "n/a" if stats["frequency"] is None else f"{stats['frequency']:.2f}"
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in (
            result["case"], result["strategy"], result["outcome"], result["original_operations"],
            result["reduced_operations"], result["actual_executions"], result["invalid_candidates"], freq,
            result["holdout_statistics"]["wilson95"])) + "</tr>")
    content = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>KernelBridge DRADD study</title><style>
body{font:15px system-ui;margin:24px;color:#222;background:#fff}h1{font-size:26px}
.table{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:8px;text-align:left;border-bottom:1px solid #ccc}
th{background:#e7f2ed}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{margin:18px 0}
</style><h1>KernelBridge / DRADD</h1><p>Controlled simulation study. Linux validation: BLOCKED.</p>
<p>Holdout rates describe fresh executions, not root-cause equivalence or schedule reproduction.
Wilson intervals assume independent Bernoulli trials; OS scheduling and shared fixtures limit that interpretation.</p>
<div class="table"><table><thead><tr><th>Case</th><th>Strategy</th><th>Outcome</th><th>Initial</th>
<th>Final</th><th>Executions</th><th>Rejected</th><th>Holdout rate</th><th>Wilson 95%</th></tr></thead><tbody>"""
    content += "".join(rows) + "</tbody></table></div><details><summary>Paired analysis</summary><pre>"
    content += html.escape(json.dumps(analysis, indent=2)) + "</pre></details></html>"
    (directory / "report.html").write_text(content, encoding="utf-8")


def study(name, output):
    output.mkdir(parents=True, exist_ok=False)
    config = {**CONFIGS[name], "trials": 5, "holdout_trials": 20, "max_executions": 120,
              "max_candidates": 100, "algorithm_seed": 809, "order_seed": 2026,
              "threshold": 0.6, "job_timeout_seconds": 45, "methods": METHODS}
    save_json(output / "configuration.json", config)
    sources = [p.relative_to(ROOT).as_posix() for folder in ("lab", "tests", "kernel", "include", "userspace")
               for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in (".py", ".c", ".h", ".sh", ".css", ".js")]
    snapshot(ROOT, output / "source", sources)
    manifest = {"kind": "DRADD_STUDY", "status": "running", "name": name,
                "platform": platform.platform(), "python": sys.version,
                "git_revision": git_output("rev-parse", "HEAD"), "git_status": git_output("status", "--porcelain"),
                "evidence_kind": "SIMULATED_FAULT", "kernel_validated": False, "jobs": [],
                "command": [sys.executable, "-m", "lab.research", "study", "--config", name, "--output", str(output)],
                "source_snapshot": "source"}
    save_json(output / "manifest.json", manifest)
    jobs = []
    product = itertools.product(config["faults"], config["seeds"], config["workers"], config["lengths"],
                                config["densities"], config.get("thresholds", [config["threshold"]]))
    for number, (fault, seed, workers, length, density, threshold) in enumerate(product):
        case = f"c{number:03d}-{fault}-s{seed}-w{workers}-n{length}-{density}-t{threshold}"
        workload = fixture(fault, seed, length, workers, density)
        for strategy in METHODS:
            jobs.append({"case": case, "strategy": strategy, "workload": workload,
                         "config": {**config, "fault": fault, "threshold": threshold,
                                    "workload_seed": seed, "probability": 0.7}})
    random.Random(config["order_seed"]).shuffle(jobs)
    results = []
    for number, job in enumerate(jobs):
        request = Path("requests") / f"{number:04d}.json"
        result_path = Path("results") / f"{number:04d}.json"
        (output / "requests").mkdir(exist_ok=True)
        (output / "logs").mkdir(exist_ok=True)
        save_json(output / request, job)
        command = [sys.executable, "-m", "lab.research", "job", "--request", str((output / request).resolve()),
                   "--output", str((output / result_path).resolve())]
        step = run_step(f"job-{number:04d}", command, (output / "source").resolve(),
                        output / "logs", config["job_timeout_seconds"])
        manifest["jobs"].append({"request": request.as_posix(), "result": result_path.as_posix(), "execution": step})
        save_json(output / "manifest.json", manifest)
        if step["status"] == "passed" and (output / result_path).exists():
            results.append(json.loads((output / result_path).read_text(encoding="utf-8")))
        print(f"{number + 1}/{len(jobs)} {job['strategy']} {job['case']} {step['status']}", flush=True)
    summary = analyze(results)
    save_json(output / "analysis.json", summary)
    report(output, results, summary)
    manifest["status"] = "complete" if len(results) == len(jobs) else "incomplete"
    save_json(output / "manifest.json", manifest)
    seal(output)
    if manifest["status"] == "complete":
        print(verify(output))
        return 0
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    run = subs.add_parser("study")
    run.add_argument("--config", choices=CONFIGS, default="smoke")
    run.add_argument("--output", type=Path, required=True)
    job = subs.add_parser("job")
    job.add_argument("--request", type=Path, required=True)
    job.add_argument("--output", type=Path, required=True)
    check = subs.add_parser("verify")
    check.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "study":
            return study(args.config, args.output)
        if args.command == "verify":
            print(verify(args.directory))
        else:
            if args.output.exists():
                raise ValueError("result already exists; use a new output path")
            execute_job(json.loads(args.request.read_text(encoding="utf-8")), args.output)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
