"""Render saved lab evidence as an offline, read-only HTML report."""

import argparse
import base64
import hashlib
from html import escape
import json
from pathlib import Path
from string import Template

from .contract import validate


def text(value):
    return escape(str(value), quote=True)


def json_block(value):
    return "<pre>" + text(json.dumps(value, indent=2)) + "</pre>"


def read_json(path):
    if path.stat().st_size > 90_000_000:
        raise ValueError(f"artifact too large: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_run(directory):
    manifest = read_json(directory / "manifest.json")
    scenario = validate(read_json(directory / "scenario.json"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest")
    if manifest.get("backend") not in ("simulated", "device"):
        raise ValueError("unknown evidence backend")
    status = manifest.get("status")
    if status not in ("running", "pass", "fail", "inconclusive"):
        raise ValueError("invalid manifest status")
    result_path = directory / "result.json"
    result = read_json(result_path) if result_path.exists() else {}
    if not isinstance(result, dict):
        raise ValueError("result must be an object")
    if status != "running" and result.get("status") != status:
        raise ValueError("manifest and result status disagree")
    history = []
    history_path = directory / "history.jsonl"
    if history_path.exists():
        if history_path.stat().st_size > 180_000_000:
            raise ValueError("history exceeds 180 MB")
        seen = set()
        with history_path.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("history entry must be an object")
                index = event.get("index")
                if (type(index) is not int or not 0 <= index < len(scenario["operations"]) or
                        index in seen or event.get("operation") != scenario["operations"][index]):
                    raise ValueError("history does not match scenario")
                seen.add(index)
                for field in ("elapsed_ns", "started_ns", "finished_ns", "worker"):
                    if field in event and (type(event[field]) is not int or event[field] < 0):
                        raise ValueError(f"invalid event {field}")
                if event.get("finished_ns", 0) < event.get("started_ns", 0):
                    raise ValueError("reversed interval")
                history.append(event)
    if status != "running" and manifest.get("operations_observed") != len(history):
        raise ValueError("manifest operation count disagrees with history")
    if status == "pass" and len(history) != len(scenario["operations"]):
        raise ValueError("passing run has missing operations")
    reduction_path = directory / "reduction.json"
    reduction = read_json(reduction_path) if reduction_path.exists() else None
    return manifest, scenario, result, history, reduction


def outcome(event):
    if "error" in event:
        return "error"
    if "expected" in event and "actual" in event:
        return "matched" if event["expected"] == event["actual"] else "mismatch"
    return "recorded"


def operation_summary(operation):
    kind = operation["op"]
    if kind == "write":
        return f"{len(operation['data']) // 2} bytes"
    if kind == "read":
        return f"up to {operation['count']} bytes"
    if kind == "resize":
        return f"{operation['capacity']} bytes"
    return ""


def operation_rows(history):
    rows = []
    for event in sorted(history, key=lambda item: item["index"]):
        state = outcome(event)
        worker = f"W{event['worker']}" if "worker" in event else "main"
        duration = event.get("elapsed_ns", event.get("finished_ns", 0) - event.get("started_ns", 0))
        operation = event["operation"]
        search = text(json.dumps(event).lower())
        rows.append(f'''<details class="operation" data-outcome="{state}" data-search="{search}">
<summary><span class="op-index" id="operation-{event['index']}">{event['index']:03d}</span><strong>{text(operation['op'])}</strong>
<span class="op-description">{text(operation_summary(operation))}</span><span class="worker">{worker}</span>
<span class="duration">{duration / 1000:.3f} us</span><span class="state {state}">{state.title()}</span></summary>
<div class="operation-body"><section><h3>Input</h3>{json_block(operation)}</section>
<section><h3>{'Expected' if 'expected' in event else 'Observation'}</h3>
{json_block(event.get('expected', {'worker': worker, 'sequence': event.get('sequence')}))}</section>
<section><h3>Actual</h3>{json_block(event.get('actual', {'error': event.get('error', 'No result')}))}</section></div></details>''')
    return "\n".join(rows)


def timeline(history):
    intervals = [event for event in history if "started_ns" in event and "finished_ns" in event]
    if not intervals:
        return ""
    origin = min(event["started_ns"] for event in intervals)
    finish = max(event["finished_ns"] for event in intervals)
    span = max(finish - origin, 1)
    rows = []
    for event in sorted(intervals, key=lambda item: (item["started_ns"], item["index"])):
        left = min(99.5, (event["started_ns"] - origin) / span * 100)
        width = min(100 - left, max(0.5, (event["finished_ns"] - event["started_ns"]) / span * 100))
        label = f"Operation {event['index']}, {event['operation']['op']}, worker {event.get('worker', 0)}"
        rows.append(f'''<div class="timeline-row"><a href="#operation-{event['index']}">{event['index']:03d} {text(event['operation']['op'])}</a>
<div class="track" role="img" aria-label="{text(label)}"><span class="bar color-{event.get('worker', 0) % 4}" style="left:{left:.4f}%;width:{width:.4f}%"></span></div>
<span class="worker">W{event.get('worker', 0)}</span></div>''')
    return f'''<section class="band"><div class="section-heading"><h2>Call intervals</h2><span>0 to {(finish - origin) / 1000:.3f} us</span></div>
<div class="timeline">{''.join(rows)}</div><p class="note">Invocation-to-completion intervals; equal timestamps may reflect clock resolution. Instrumented timings are not benchmarks.</p></section>'''


def render_report(directory):
    manifest, scenario, result, history, reduction = load_run(directory)
    status = manifest["status"]
    labels = {"pass": "Contract pass", "fail": "Contract failure", "inconclusive": "Inconclusive", "running": "Incomplete capture"}
    simulated = manifest.get("backend") == "simulated"
    evidence = "SIMULATED EVIDENCE" if simulated else "LINUX DEVICE CAPTURE"
    scope_note = ("Simulator results validate the lab tooling, not the Linux driver." if simulated else
                  "This capture covers only the declared contract. It is not overall kernel validation.")
    reason = result.get("error") or result.get("reason")
    if not reason:
        reason = {"pass": "The recorded operations satisfy the declared contract.",
                  "fail": "An observation does not match the declared contract.",
                  "inconclusive": "The available evidence does not establish a pass or failure.",
                  "running": "This run has no final verdict. Completed records are shown below."}[status]
    if "failure_index" in result:
        reason = f"Operation {result['failure_index']}: {reason}"
    witness = result.get("witness_order")
    witness_html = ""
    if isinstance(witness, list):
        witness_html = '<section class="band"><h2>Valid FIFO ordering</h2><div class="witness">' + "".join(
            f'<a href="#operation-{text(index)}">{text(index)}</a>' for index in witness) + '</div><p class="note">One legal explanation of the captured calls; not a trace of internal kernel execution.</p></section>'
    reduction_html = ""
    if isinstance(reduction, dict):
        reduction_html = f'''<section class="band"><h2>Failure reduction</h2><p>{text(reduction.get('original_operations', '?'))} operations reduced to
<strong>{text(reduction.get('reduced_operations', '?'))}</strong> in {text(reduction.get('attempts', '?'))} attempts.
Confirmation: <strong>{'reproduced' if reduction.get('confirmed') is True else 'not confirmed'}</strong>.</p>
<details><summary>Reduction evidence</summary>{json_block(reduction)}</details></section>'''
        if "trials_per_candidate" in reduction:
            reduction_html += f'''<section class="band"><h2>Repeated executable replay</h2>
<p>{text(reduction.get('outcome'))}. Strategy: {text(reduction.get('strategy'))}.
Final matching-failure rate: {text(reduction.get('replay_success_rate'))}.
Trials per group: {text(reduction.get('trials_per_candidate'))}; total trials: {text(reduction.get('total_trials'))}.</p>
<p>Source: {text(reduction.get('evidence_kind'))}. Controlled start only; not deterministic replay or root-cause proof.</p>
<p>Total operations executed: {text(reduction.get('total_operations_executed'))}; search transitions: {text(reduction.get('search_transitions'))}.</p></section>'''
    history_reduction_path = directory / "history-reduction.json"
    if history_reduction_path.exists():
        recorded = read_json(history_reduction_path)
        reduction_html += f'''<section class="band"><h2>Recorded history reduction</h2>
<p>{text(recorded.get('classification'))}. This is a retained observation prefix, not an executable reproducer.</p>
<details><summary>Recorded counterexample evidence</summary>{json_block(recorded)}</details></section>'''
    css = Path(__file__).with_name("report.css").read_text(encoding="utf-8")
    script = Path(__file__).with_name("report.js").read_text(encoding="utf-8")
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    document = Template('''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-$digest'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>KernelBridge | $title</title><style>$css</style></head><body>
<a class="skip" href="#history">Skip to operations</a>
<header><div class="brand">KernelBridge <span>Evidence Lab</span></div><nav aria-label="Report sections"><a href="#overview">Run</a><a href="#history">Operations</a><a href="#provenance">Provenance</a></nav></header>
<main><section id="overview" class="overview"><div class="eyebrow">$evidence</div><div class="title-line"><h1>$title</h1><span class="verdict $status">$label</span></div>
<p class="reason">$reason</p><p class="scope">$scope_note</p>
<dl class="metrics"><div><dt>Recorded / planned</dt><dd>$observed / $planned</dd></div><div><dt>Workers</dt><dd>$workers</dd></div>
<div><dt>Initial capacity</dt><dd>$capacity <small>bytes</small></dd></div><div><dt>Search transitions</dt><dd>$explored</dd></div></dl>
<div class="run-meta"><span>$scope</span><span>$started</span></div></section>
$timeline$witness$reduction
<section id="history" class="band"><div class="section-heading"><h2>Operations</h2><span id="visible-count" aria-live="polite">$observed records</span></div>
<div class="filters"><div class="filter-field"><label for="search">Search operations</label><input id="search" type="search" autocomplete="off"></div>
<div class="filter-field"><label for="outcome">Outcome</label><select id="outcome"><option value="all">All outcomes</option><option value="mismatch">Mismatch</option><option value="matched">Matched</option><option value="recorded">Recorded</option><option value="error">Error</option></select></div></div>
<div class="operation-labels" aria-hidden="true"><span>ID</span><span>Call</span><span>Request</span><span>Worker</span><span>Duration</span><span>Observation</span></div>
<div id="operations">$rows</div><p id="empty" $empty_hidden>No matching operations.</p>
<noscript><p>All recorded operations are displayed. Filtering requires JavaScript.</p></noscript></section>
<section id="provenance" class="band"><h2>Provenance</h2><dl class="provenance"><dt>Backend</dt><dd>$backend</dd><dt>Fixture fault</dt><dd>$fault</dd><dt>Platform</dt><dd>$platform</dd><dt>Revision</dt><dd><code>$revision</code></dd></dl>
<details><summary>Full manifest and source hashes</summary>$manifest</details><details><summary>Result evidence</summary>$result</details></section>
<footer>KernelBridge / $scope</footer></main><script>$script</script></body></html>''')
    rows = operation_rows(history)
    return document.substitute(
        digest=digest, title=text(directory.name), css=css, status=status, label=labels[status],
        evidence=evidence, reason=text(reason), scope_note=scope_note, observed=len(history),
        planned=len(scenario["operations"]), workers=text(manifest.get("workers", 1)),
        capacity=scenario["capacity"], explored=text(result.get("explored", "n/a")),
        scope=text(manifest.get("scope", "unspecified")), started=text(manifest.get("started_utc", "unknown")),
        timeline=timeline(history), witness=witness_html, reduction=reduction_html, rows=rows,
        empty_hidden="hidden" if history else "", backend=text(manifest.get("backend", "unknown")),
        fault=text(manifest.get("fixture_fault", "none")), platform=text(manifest.get("platform", "unknown")),
        revision=text(manifest.get("git_commit") or "unavailable"), manifest=json_block(manifest),
        result=json_block(result), script=script)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or args.directory / "report.html"
    try:
        report = render_report(args.directory)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
