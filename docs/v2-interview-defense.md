# V2 technical walkthrough

Use this with interview-defense.md, which covers driver locking, user-copy,
wait queues, poll, lifetime and ABI. The v2 additions do not replace those answers.

## Five-to-ten-minute demonstration

1. Explain the virtual shared FIFO and the kernel/userspace boundary. State that
   Linux runtime acceptance is currently blocked; no hardware or production use.
2. Run the correct-fixture demo and show a witness ordering. Explain that the
   order is a legal explanation, not the observed kernel scheduler trace.
3. Run the false-EOF demo. Show original observations, then the one-operation
   executable reproducer and its fresh confirmation trials.
4. Show recorded-history reduction separately. It trims only at quiescent cuts
   and is not called an executable reproducer.
5. Compare the 240-run study: equal sizes, lower pooled work for longer fixtures,
   but 28 pairs with more chunk candidate checks. Explain why this is not a
   breakthrough or universal advantage.
6. Show exact source snapshots, failed device preflight and the quality gate.
   Describe the next real Linux experiment and what result would change a claim.

## Challenging follow-ups

**Why not remove arbitrary recorded operations?** A read could depend on a
concurrent write that was removed. The new reducer uses quiescent prefix cuts;
no excluded operation overlaps the retained prefix. This conservatism limits
minimization but prevents that invented counterexample. Executable reduction
instead starts a new device state and re-observes every candidate.

**What does 3/3 reproduction prove?** Only three matching observations in the
declared fixture/environment. It is not deterministic replay, a rare-race
probability estimate, or preservation of one root cause. The signature is a
FIFO contract-failure class. The rate now counts matching failures only.

**How do you measure reducer cost?** Candidate groups, actual operations captured,
search transitions and wall time are separate counters. Three trials of a long
candidate can cost more than several shorter checks. The study includes cases
where chunk deletion uses more checks or more time.

**Does seeded jitter control scheduling?** No. It controls requested delay values
and the initial workload, not when the OS runs threads or when a syscall takes
the kernel mutex. The common barrier controls start readiness only.

**What happens when a worker has a programming error?** Ordinary exceptions are
retained in its event and the run is inconclusive. A malformed result becomes
INVALID_CAPTURE. KeyboardInterrupt/SystemExit are not swallowed as ordinary
backend errors. An external watchdog bounds initial execution.

**Why not model SET_MODE now?** The generic adapter uses O_NONBLOCK on all calls,
so changing global mode would not test the interesting blocking transition.
Existing C regression tests cover the intended wakeup behavior, but have not run
on Linux here. Adding it to the model would otherwise overstate coverage.

**How is interrupted write checked?** Fill the FIFO, launch a blocking writer,
observe blocked_writes increment, send SIGUSR1 with no SA_RESTART, join, require
EINTR and unchanged occupancy. The test runs under the integration suite timeout;
its implementation is not yet compiled or executed on this host.

**Can a sanitizer finding be linked to a mismatch?** Co-occurrence is not root
cause. Capture the exact module, config, workload, timing and independent
diagnostics, then isolate the issue. Automatic kernel correlation is not yet
implemented and no diagnostic kernel has run here.

**Why not write a native benchmark or lock-free FIFO?** There is no Linux profile
showing either is the limiting factor. The Windows Python results validate the
harness and describe that host, not ringbuf_char performance. Measure first.

**What is differentiated?** A small auditable device and explicit contract joined
to fresh-execution reduction, conservative recorded evidence, repeatable studies
and honest uncertainty. Linearizability checking, delta debugging and kernel
fault injection are established techniques, not inventions of this project.
