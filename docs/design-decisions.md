# Design Decisions

## Character Device

A character device is a good fit because the project models byte-stream I/O
without block-device sector semantics or network-stack policy. It exercises the
VFS interface that many real kernel drivers expose to user space.

## Partial Writes

Writes use normal stream-style partial semantics. If space exists, the driver
writes as much as the buffer can currently accept and returns that byte count.
If no space exists, blocking descriptors wait and non-blocking descriptors
receive `-EAGAIN`.

This policy avoids surprising large sleeps for huge writes and teaches callers
to handle short writes correctly.

## Mutex Instead of Spinlock

The shared state is protected with a mutex because `copy_to_user`,
`copy_from_user`, and memory allocation paths may sleep. A spinlock would be
wrong around those operations. The critical sections are small and the device
is a teaching/portfolio driver, so a mutex is clear and appropriate.

## Wait-Queue Design

Separate reader and writer wait queues make readiness events explicit. Readers
are woken after writes. Writers are woken after reads, clears, and successful
resizes. Blocking code checks state, releases the mutex, sleeps, and then
rechecks state after wakeup.

## ABI Versioning

Ioctl ABIs are difficult to change after user-space programs depend on them.
The stats structure carries `abi_version` and `struct_size`, uses fixed-width
Linux integer types, and avoids pointers. This gives future versions a clear
compatibility boundary.

## Resize Behavior

Resize preserves unread data when possible by linearizing the old circular
contents into the new allocation. A resize below the unread byte count is
rejected instead of silently dropping data.

## Rate-Limited Logs

Normal reads and writes do not log. Fault paths use rate-limited warnings so a
bad user process cannot flood `dmesg`. Important lifecycle and resize events
use `pr_info`.

## Virtual Device Scope

The driver is not tied to physical hardware. That keeps the project runnable in
a disposable VM while still demonstrating core driver mechanics. A PCIe, USB,
or platform version would add bus probing, hardware resource management,
interrupt handling, DMA constraints, and device-specific power management.

## Security Choices

The driver does not trust user-provided pointers or sizes. It uses
`copy_to_user` and `copy_from_user`, validates ioctl command numbers, rejects
invalid capacities, does not expose kernel addresses, does not return
uninitialized padding, and keeps `/dev/shivam_char` permissions controlled by
udev/root unless the load script is explicitly asked to relax them for a
throwaway local test VM.

