# Design Decisions

These are the choices I would expect to be asked about in a review or
interview. Most of them are not exotic; they are the boring choices that keep a
small driver understandable.

## Why a Character Device

The driver exposes a byte stream, so a character device fits naturally. A block
device would add sector semantics that do not belong here, and a network device
would pull in a completely different stack. This project is about the VFS path
and user/kernel boundary.

## Partial Writes

Writes are partial. If 100 bytes are requested and only 30 bytes fit, the
driver writes 30 and returns 30. If no bytes fit, it either waits or returns
`-EAGAIN`, depending on blocking mode.

That behavior is easier to compose with normal Unix I/O loops. It also makes
the user-space client handle short writes instead of assuming the kernel did
everything in one call.

## Mutex Instead of Spinlock

The driver uses a mutex because the protected paths can sleep. User-copy
helpers may fault and sleep, resize allocates memory, and blocking paths need
to drop the lock before waiting.

A spinlock would be the wrong tool around those operations. If this were an
interrupt-driven hardware driver, the split between spinlocks, mutexes, and
work queues would need more careful design.

## Wait Queues

Readers and writers have separate wait queues because they wait on different
conditions. Readers need data. Writers need free space.

The important part is not the wait queue itself; it is the lock choreography.
The driver checks state under the mutex, releases the mutex before sleeping,
and then checks again after waking. That avoids sleeping while holding the
state lock and handles spurious or stale wakeups.

## IOCTL ABI Shape

The ioctl header uses fixed-width Linux types and avoids pointers in exported
structures. The stats payload carries an ABI version and the structure size.

That may look formal for a sample driver, but ioctl interfaces tend to outlive
the original code. It is better to leave a version marker on day one than to
wish one existed later.

## Resize Behavior

Resize keeps unread data if the new capacity can hold it. If it cannot, the
driver rejects the request instead of dropping data silently.

The implementation copies the unread circular contents into a new linear
allocation, then swaps it into the buffer state while holding the mutex.

## Logging

Normal read and write calls stay quiet. They are too frequent for useful logs.
Load, unload, resize, and mode changes use `pr_info`. Bad user-copy and
unsupported ioctl paths use rate-limited warnings so a broken process cannot
fill `dmesg` in a tight loop.

## Security Choices

The driver does not trust user pointers or user-provided capacities. It uses
`copy_to_user` and `copy_from_user`, validates ioctl command numbers, zeroes
the stats structure before returning it, and never exposes kernel addresses.

The load script leaves device permissions alone unless `--chmod` is passed.
That option is only there to make local VM testing less annoying.

## Why No Hardware

Keeping the device virtual makes the project reproducible. Anyone with a Linux
VM and matching kernel headers can build it. A hardware-backed version would
need probe/remove callbacks, register access, interrupts, DMA rules, and power
management. Those are valuable topics, but they would hide the core character
device path this project is focused on.

