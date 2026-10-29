# Research positioning

Primary-source review: 2026-10-25. This is a focused comparison, not a systematic
literature review. No novelty or first-of-its-kind claim is supported.

| Existing work | Relevant capability | KernelBridge boundary |
| --- | --- | --- |
| [Porcupine](https://github.com/anishathalye/porcupine) | Executable sequential specifications, concurrent history checking and visualization | Our small bounded DFS is an educational FIFO-specific checker, not a performance replacement |
| [syzkaller reproduction](https://github.com/google/syzkaller/blob/master/docs/reproducing_crashes.md) and [minimization](https://github.com/google/syzkaller/blob/master/prog/minimization.go) | Re-execution and minimization of kernel crash reproducers | Our oracle checks a byte-stream contract; we have not found or reproduced a kernel crash |
| [KUnit](https://docs.kernel.org/dev-tools/kunit/index.html) | In-kernel unit testing | Buffer helper tests complement, not replace, syscall integration |
| [Kernel fault injection](https://www.kernel.org/doc/html/latest/fault-injection/fault-injection.html) | Existing controlled failure mechanisms | Reuse these in a disposable guest; no custom kernel corruption hooks |
| [Ioctl guidance](https://docs.kernel.org/driver-api/ioctl.html) | UAPI layout, compatibility, command design | Fixed-width layout assertions are only one part of ABI verification |

The defensible contribution is integration: a small auditable driver, a declared
contract subset, repeatable workload capture, uncertainty-aware checking, and
fresh-execution reduction. All individual techniques have prior art.

Initial research question: does a more elaborate reducer produce smaller or
cheaper reproductions than straightforward deletion? Before building a custom
failure-aware algorithm, the study compares ordinary chunk deletion with single
deletion under identical replay and search budgets. It establishes a baseline,
not a new algorithm. Results in [experimental-results.md](experimental-results.md)
show equal final sizes on the selected corpus. That does not justify adding a
dependency solver or kernel scheduler instrumentation now.

Real-device evaluation is deferred until the Linux baseline passes. Simulator
fixtures are deliberately simple and do not establish rare-race reproducibility,
scalability, or an advantage over existing research tools.
