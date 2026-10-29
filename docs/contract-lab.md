# KernelBridge contract lab

The lab compares observable device behavior with a reference FIFO model. The
first version covers sequential nonblocking reads, writes, clear, resize, and
capacity queries. A bounded deletion reducer preserves an observed failure
signature and emits a smaller scenario. It does not promise globally minimal
tests or deterministic kernel scheduling.

## Portable demonstration

Python 3.10 or later, standard library only. Run from the repository root:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m lab.runner --seed 42 --steps 300 --output artifacts/reference
python3 -m lab.runner --seed 42 --steps 300 --fault reverse-read --reduce --output artifacts/fault
python3 -m lab.runner --scenario artifacts/fault/reduced.json --fault reverse-read --output artifacts/replay
```

The first run uses an independent deque simulator. The latter two intentionally
fail against a reverse-read fixture. These results test the lab, not the kernel.
Other fixtures are false-eof and resize-loss. They represent artificial defects;
they do not establish that these bugs exist in a released driver.

Exit codes: 0 means the declared contract passed, 1 means a behavioral mismatch,
and 2 means inconclusive or invalid invocation. An interrupted run remains
marked running in its manifest and must not be counted as a pass.

## Linux device run

Use a disposable Linux VM, matching kernel headers, Python 3.10+, and the usual
C build tools. Build/load the module, then:

```sh
make userspace
sudo timeout 30 python3 -m lab.runner --backend device --exclusive --seed 42 --steps 300 --output artifacts/device
```

The exclusive flag acknowledges that this run clears all buffered data. It
does not lock out other processes: ensure no other clients are using the device.
The adapter opens O_NONBLOCK, saves capacity, clears the buffer, sets the initial
capacity, and restores capacity/clears again on ordinary exit. Data is not
restored. Forced termination can skip cleanup; reset the VM or reload the module
before another run. Existing global mode is not changed.

The ABI helper is compiled from the actual UAPI header. No ioctl numbers are
hardcoded in Python. Use the helper built for the tested kernel/userspace
architecture. A mismatch, missing device, allocation failure, or I/O failure
is not a passing result. ENOMEM, EINTR, ENODEV, and EIO produce inconclusive runs.
Other unexpected errno values are contract mismatches and need investigation.

## Evidence and replay

Each new output directory contains:

- scenario.json: complete operations, initial capacity, format version, seed
- manifest.json: backend, fixture, platform, Python, Git state, source hashes
- history.jsonl: expected/observed results and per-operation elapsed time
- result.json: status and first mismatch signature, or environment error
- reduced.json and reduction.json when failure reduction is requested

Output directories cannot be reused. Input operations are validated before the
device is opened. Completed history entries are flushed as they occur. A source
hash identifies local files, not the loaded module: record the module hash,
kernel config, compiler, and boot logs separately for a release evaluation.
Durations include instrumentation and are diagnostic data, not benchmarks.
New captures use Python's high-resolution monotonic performance counter, with
its resolution recorded in the manifest. Earlier Windows captures using
monotonic_ns may have zero-duration intervals due to coarse clock resolution.

Replay uses the saved scenario rather than regenerating from its seed. Reduction
reinitializes the backend for every attempt and stops at 100 candidate runs.
The same operation, mismatching result fields, and errno pair must recur. This
signature is an observed symptom, not proof of the same root cause. The final
candidate is replayed once and its confirmation status saved; flaky failures
need repeated reproduction trials before any claim of reliability.

## Local evaluation (2026-10-10)

On the Windows development host, seed 42 with 300 operations passed against the
simulator. With the reverse-read fixture, the first mismatch occurred at the
eighth operation. Nine reduction attempts produced a two-operation write/read
scenario, and a separate CLI replay reproduced the mismatch. Evidence is in
artifacts/reference, artifacts/fault, and artifacts/replay (ignored by Git).
These are fixture results, not driver performance or kernel-validation results.

## Offline evidence reports

```sh
python3 -m lab.report artifacts/fault
python3 -m lab.report artifacts/concurrent
```

Open the resulting report.html directly in a browser. No server, network assets,
or installation is needed to view it. The report includes searchable operation
records, expandable input/expected/actual data, reduction evidence, concurrent
call intervals, and a valid FIFO ordering when one was found. Concurrent calls
are labeled Recorded individually: the checker evaluates the history as a whole.

The report validates artifact structure and consistency but does not re-execute
the checker. Use lab.history for independent offline rechecking of concurrent
histories. Incomplete captures remain visibly incomplete. Untrusted artifact
text is escaped, and a content security policy allows only the bundled script.
The output is created exclusively; existing reports or evidence are never
overwritten. Use --output with a new filename to regenerate a report.

Report tests are included in the standard Python suite. Optional visual and
interaction checks use Playwright: node tests/report_browser.cjs, after generating
the two reports above. REPORT_CHROMIUM may point to an installed compatible
Chromium executable. The checks cover 320, 390, 768, and 1440 pixel widths.

## Bounded concurrent histories

```sh
python3 -m lab.runner --workers 3 --steps 12 --seed 42 --output artifacts/concurrent
python3 -m lab.history artifacts/concurrent
python3 -m lab.runner --workers 2 --scenario tests/fixtures/concurrent_empty.json --fault false-eof --output artifacts/concurrent-fault
```

The last command is an intentionally failing simulator demonstration. For Linux,
add --backend device --exclusive to a normal run, with an external timeout as
above. Device calls are not serialized by a userspace lock. Each worker issues
its assigned operations in order after a common start barrier. The simulator
uses its own lock to implement the reference device's atomic-operation contract;
Python scheduling is not evidence of kernel contention.

Each recorded call has invocation/completion timestamps, worker and sequence
numbers, input, and result. The checker explores sequential explanations that
preserve definitely nonoverlapping calls and each worker's program order. A pass
includes witness_order: operation indexes in one valid linearization. It does
not claim that this is the actual kernel execution order. Equal timestamps from
different workers are conservatively treated as overlap.

At most 12 calls and 2..4 workers are supported per concurrent run. Depth-first
search has factorial worst-case cost and is limited to 10,000 candidate
transitions by default. Search exhaustion, missing calls, and worker exceptions
are inconclusive. A fail requires exhaustive rejection of all eligible orders.
Use --search-budget to adjust the bound, up to 100,000. Offline rechecking can
increase that budget without invoking the device or changing original evidence.
It verifies scenario/history agreement before checking a completed capture.

Re-executing the saved scenario does not reproduce thread scheduling. Sequential
failure reduction is intentionally disabled for concurrent runs. Calls that hang
inside the kernel still require an external process/VM watchdog; the start
barrier timeout only handles workers failing to reach the barrier.

The checker is tested against explicit FIFO violations and a separate exhaustive
permutation oracle for 40 small histories. That provides implementation evidence,
not a formal proof of the checker or driver.

## Scope limits

This version checks only bounded complete histories of the declared nonblocking
operations. It does not check blocking/wakeup behavior, poll, bad pointers,
statistics, device isolation, or kernel memory safety. Existing
integration and regression tests cover some of those independently. A passing
lab scenario cannot replace KUnit, sanitizers, lockdep, or driver review. Linux
runtime captures and debug-kernel evidence remain outstanding.
