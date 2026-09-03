# System Design Tradeoffs

## Virtual Driver vs Hardware Driver

Chosen: virtual driver.

Reason: it is easy to build in a VM and focuses attention on character-device
mechanics. A hardware driver would be more realistic but much harder for other
people to run.

Tradeoff: it does not demonstrate interrupts, DMA, register access, or bus
probe/remove flows.

## Shared Buffer vs Per-Open Buffer

Chosen: one shared device buffer.

Reason: it makes concurrent reader/writer behavior visible and easy to test.

Tradeoff: one process can consume bytes written by another process. A per-open
buffer would provide isolation but would hide shared-device synchronization.

## Mutex vs Spinlock

Chosen: mutex.

Reason: user-copy and allocation paths may sleep. A mutex fits process-context
file operations.

Tradeoff: a mutex has more scheduling overhead than a spinlock, but that is the
right cost for sleepable paths.

## Partial Writes vs All-or-Nothing Writes

Chosen: partial writes.

Reason: this matches normal stream-device behavior and forces user space to
handle short writes correctly.

Tradeoff: callers that want message boundaries must frame their own data.

## Ioctl vs Sysfs for Control

Chosen: ioctl for active controls and stats.

Reason: clear, resize, mode change, and stats snapshots are naturally tied to a
device file descriptor.

Tradeoff: ioctl ABIs need careful versioning. A future version could add
read-only sysfs attributes for simple inspection.

## Database vs In-Kernel State

Chosen: in-kernel volatile state only.

Reason: the driver is a kernel module, not a service. Adding a database would
be unrelated to the current product.

Tradeoff: stats and buffered data disappear on unload.

## Hosted CI vs Privileged VM Tests

Chosen: hosted CI for user-space build/static checks, local VM for integration.

Reason: GitHub-hosted runners should not load arbitrary kernel modules.

Tradeoff: full confidence requires a separate privileged VM test run.

