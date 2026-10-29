# V2 reproducible workflow

Use Python 3.10+ from the repository root. Output directories must be new.
All commands below use simulation unless explicitly selecting device mode.

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m lab.demo --seed 42 --repeats 3 --output artifacts/demo-control
python3 -m lab.demo --fault false-eof --read-percent 100 --write-percent 0 --control-percent 0 --jitter-us 100 --repeats 3 --output artifacts/demo-fault
python3 -m lab.experiment --matrix-v2 --output artifacts/study-v2
```

Open demo-fault/run-00/report.html. It is self-contained, with no network assets.
The original history, executable reduction trials, matching rate, and separate
recorded counterexample appear together. Full candidate results are expandable;
the manifest contains the exact runner command, source hashes and environment.
The top-level demo manifest retains generation settings and repetition outcomes.

COMPLETE means the demo pipeline completed, even when the expected contract
result is CONTRACT_MISMATCH. It never means the driver is correct. Individual
runner exit 1 means mismatch; exit 2 means inconclusive. Demo exit 0 means all
runs have conclusive contract observations; its exit 2 means blocked/inconclusive.
HARNESS_FAILURE and INVALID_CAPTURE must not be relabeled kernel defects.

Generation supports --steps 1..12, --workers 2..4, --seed, --payload 0..4096,
--capacity 256..65536, percentage weights for read/write/control, and --jitter-us
0..10000. Remaining probability selects capacity queries; controls select clear
or resize (including a rejected resize). Percentages are sampling probabilities,
not guaranteed exact counts in a small workload. Delays are chosen reproducibly
per worker outside invocation intervals; the scheduler is still uncontrolled.
Blocking mode is intentionally unsupported in this bounded generator.

Each initial execution has a 60-second process watchdog. Simulated reduction is
bounded to 20 candidate groups with three trials and a finite checker budget;
use an external wall-clock timeout for the whole CLI when operating unattended.
Source snapshots retain lab Python and report CSS/JS, not an entire runtime image.

Real-device execution, only in an authorized disposable guest:

```sh
sudo python3 -m lab.validate_linux --integration --output artifacts/linux-runtime
sudo python3 -m lab.demo --backend device --exclusive --output artifacts/device-demo
```

The first command establishes build/runtime/diagnostics evidence. The second
executes the existing O_NONBLOCK adapter and does not load a module or silently
fall back to a simulator. It needs the loaded device and compiled abi_dump from
a separately prepared guest checkout. It does not yet run executable reduction
on the device or correlate diagnostics automatically. Module identity remains
UNVERIFIED in that demo until explicitly tied to Linux validation evidence.

Optional browser QA: install/use Playwright and Chromium, set REPORT_CHROMIUM
when a custom executable is needed, then run `node tests/v2_report_browser.cjs`.
The test expects the retained artifacts/v2-demo-fault and v2-demo-control bundles.
