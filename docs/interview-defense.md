# Interview defense

## Short explanation

KernelBridge is a virtual Linux character driver plus a validation lab. The
driver implements a bounded shared FIFO with blocking I/O, poll and ioctl
controls. The lab checks an explicit nonblocking contract, searches bounded
concurrent histories, and reduces simulated failures by re-executing smaller
workloads. Portable evidence is available; Linux runtime validation is blocked
on the current machine. It is a systems-learning project, not production use.

## Technical questions

**Why a mutex, not a spinlock?** User copies and allocation can sleep. The single
mutex makes FIFO and resize reasoning straightforward, at a latency cost that
must be measured before redesign.

**What if copy_to_user partially succeeds?** Consume only the copied prefix.
Return a positive short count when any bytes moved; otherwise EFAULT. The same
principle applies to write commits. Linux mprotect regression exists, unrun here.

**Where does a write linearize? Can read overlap resize?** FIFO updates occur
inside one critical section; the final commit is a suitable abstract point for
accessible-memory writes. Calls may overlap in time, but their buffer mutations
cannot run concurrently under that mutex.

**What prevents lost wakeups after CLEAR?** The waiter snapshots generation under
the mutex, unlocks, enters wait_event_interruptible, and rechecks its predicate.
Controls change generation and wake both queues. Wakeup is a hint; an empty read
must retry, not invent EOF. Linux stress validation remains outstanding.

**Can rmmod free a device with an open descriptor?** Normal module references via
owner prevent that unload. Forced unload is unsupported, not a tested shutdown
protocol. The shutdown flag does not replace lifetime management.

**How does poll work?** Register both queues, then inspect occupancy/capacity
under the mutex. Readiness can change before the caller acts on it.

**Why short writes? What does O_NONBLOCK promise?** The FIFO accepts the fitting
prefix rather than waiting to fit the whole request. Nonblocking returns EAGAIN
only when no readiness progress is possible; mutex/page-fault latency can remain.

**What does the C concurrency test prove?** It checks framed/checksummed traffic
under its workload. Same-side userspace locks limit interleavings. It is neither
a broad race detector nor a contention benchmark.

**Serializability versus linearizability?** Both seek a sequential explanation;
linearizability also respects completed-before-invoked real-time order. Our
checker enforces that and each worker's program order.

**How can the checker be wrong?** An incorrect model, missing events, timestamp
errors, unsupported semantics, or oracle bugs can mislead it. Incomplete captures
and exhausted budgets are inconclusive. A small permutation oracle checks the
search but shares the model, so it cannot eliminate specification mistakes.

**Is reduction equivalent to reproducing a race?** No. Deleting recorded events
can create impossible observations. We execute every candidate from empty state,
retain worker order, and run fresh confirmation trials. The CLI currently does
this only in simulation; it does not control a kernel scheduler or prove a cause.

**Why exclude stats from linearizability?** Individual counters update outside
the buffer lock, and reset is not a multi-counter transaction. Treating all fields
as one exact snapshot would impose a contract the implementation does not offer.

**Is the ioctl ABI portable?** Fixed-width fields, explicit sizes, reserved output
zeroing, and compile-time layout checks help. No compat_ioctl exists, so I do not
claim 32-bit-on-64-bit compatibility. ABI version fields do not make arbitrary
layout changes backward-compatible; use a new ioctl when necessary.

**Does the Python benchmark measure kernel cost?** No: end-to-end round trips
include interpreter and scheduling. A native harness is justified only when a
specific measurement question needs it. There is no Linux device baseline yet.

**What does KCSAN add?** Dynamic detection of data races on executed paths, unlike
functional model tests. It has not run here. KASAN targets memory errors; lockdep
checks locking dependencies. None proves complete correctness from a clean run.

**How would you investigate a lockup?** Preserve serial console, kernel config,
source/module identity, task stacks and lock diagnostics in a disposable guest;
compare a minimal workload, use an external watchdog, and retain failed runs.
Do not assume killing a userspace process recovers a wedged kernel.

**How would you reproduce a rare failure?** Preserve workload and worker ownership,
repeat bounded attempts, record success/failure/inconclusive counts, perturb one
condition at a time, and compare signatures cautiously. Deterministic kernel
replay is not implemented.

**Why an independent simulator?** Different data structures reduce shared
implementation mistakes: bytearray model versus deque fixture. They still share
the written specification and cannot substitute for exercising the C driver.

**What result can you defend now?** A 40-run simulated deletion comparison found
equal final sizes but fewer median candidate checks with chunk deletion. It is
not a new algorithm, kernel bug discovery, or general performance result.

**Strongest limitation?** Linux runtime evidence is missing. My next acceptance
gate is the snapshot validation runner in a disposable guest, then KUnit and
diagnostic kernels. I would say that directly rather than claim production quality.

## Demonstration

Run the portable suite, the study, and a concurrent runner/report as documented
in concurrency-model.md. Show a failing simulated fixture alongside the correct
control. Open a saved candidate to explain why the write survives reduction.
Then show the blocked Linux manifest and explain the exact next validation gate.
