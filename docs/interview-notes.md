# Interview Notes

## What is a character device?

A character device exposes a byte-oriented interface through file operations
such as `open`, `read`, `write`, `ioctl`, and `poll`. It is useful when the
device is naturally a stream or command endpoint rather than a block-addressed
storage device.

## What are major and minor numbers?

The major number identifies the driver associated with a device node. The minor
number identifies a specific device instance handled by that driver. This
project allocates both dynamically with `alloc_chrdev_region`.

## What does cdev_add do?

`cdev_add` registers a `struct cdev` with the kernel so VFS operations on the
device number are dispatched to the driver's `file_operations`.

## How does a system call reach the driver?

A process calls `read`, `write`, `ioctl`, or `poll` on a file descriptor. The
VFS resolves the descriptor to a `struct file`, finds the attached
`file_operations`, and invokes the matching driver callback.

## What is struct file_operations?

It is the driver's method table for VFS operations. This project implements
`open`, `release`, `read`, `write`, `unlocked_ioctl`, `poll`, and `llseek`.

## Why use copy_to_user and copy_from_user?

User pointers are not ordinary kernel pointers. These helpers safely transfer
data across the kernel/user boundary and report faults instead of letting the
kernel directly dereference invalid user memory.

## Why can kernel code not directly dereference user pointers?

User memory can be unmapped, swapped, maliciously invalid, or inaccessible from
kernel context. Direct dereference can crash the kernel or create security
bugs. The copy helpers perform access checks and fault handling.

## What is the difference between a mutex and a spinlock?

A mutex can sleep while waiting and is suitable for process context. A spinlock
busy-waits and is suitable for short atomic sections or interrupt context. This
driver uses a mutex because user-copy and allocation paths may sleep.

## Why are wait queues needed?

Wait queues let blocking reads sleep until data is available and blocking
writes sleep until space is available. They avoid wasteful polling loops in the
kernel.

## How is O_NONBLOCK handled?

If `O_NONBLOCK` is present and the operation cannot proceed immediately, read
or write returns `-EAGAIN`. The driver also supports a global ioctl mode that
forces non-blocking behavior.

## How does poll work?

The driver calls `poll_wait` to register the caller on its wait queues and then
returns readiness bits. Data available maps to `POLLIN | POLLRDNORM`; free
space maps to `POLLOUT | POLLWRNORM`.

## What is ioctl?

`ioctl` is a control interface for device-specific operations that do not fit
cleanly into read/write. This driver uses it for clear, stats, capacity, mode,
and counter reset.

## Why must ioctl ABIs be versioned carefully?

Once applications compile against ioctl numbers and structures, changing them
can break those applications. This project includes an ABI version and
structure size in the stats payload.

## How are race conditions prevented?

Buffer state is protected by a mutex. Counters use `atomic64_t`. Blocking paths
drop the mutex before sleeping and recheck conditions after wakeup.

## How is module cleanup handled?

Cleanup wakes waiters, destroys the device node and class, deletes the `cdev`,
unregisters the device number, frees buffer memory, and frees the driver
context.

## What happens when rmmod is attempted while the device is open?

The `.owner = THIS_MODULE` reference in `file_operations` keeps the module
referenced while file handles exist. Normal `rmmod` fails with the module busy.

## How would this design change for a real PCIe, USB, or platform device?

The virtual buffer would be replaced or supplemented by hardware register
access, interrupt handling, DMA mapping, bus probe/remove callbacks, runtime
power management, and device-tree/ACPI or bus-specific enumeration.

## What are the limitations of this virtual character driver?

It does not communicate with hardware, does not implement per-open private
buffers, and does not provide message atomicity. It is a robust byte-stream
driver intended to demonstrate kernel interfaces, synchronization, and testing.

