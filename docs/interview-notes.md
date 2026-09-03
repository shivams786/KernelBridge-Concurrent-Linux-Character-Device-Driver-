# Interview Notes

These are short answers I would use to explain the project without reading the
code line by line.

## What is a character device?

A character device is a byte-oriented kernel interface exposed through a device
node such as `/dev/ringbuf_char`. User space talks to it with familiar file
operations: `open`, `read`, `write`, `ioctl`, and `poll`.

## What are major and minor numbers?

The major number selects the driver. The minor number selects a specific device
handled by that driver. This module asks the kernel for a free pair with
`alloc_chrdev_region`.

## What does cdev_add do?

`cdev_add` makes the initialized `struct cdev` live. After that, VFS operations
on the registered device number can reach the driver's `file_operations`.

## How does a system call reach the driver?

The process calls into the kernel with a file descriptor. The VFS finds the
underlying `struct file`, looks at its `file_operations`, and calls the matching
driver method.

## What is struct file_operations?

It is the callback table for a file-like kernel object. In this driver it
contains `open`, `release`, `read`, `write`, `unlocked_ioctl`, `poll`, and
`no_llseek`.

## Why use copy_to_user and copy_from_user?

User pointers are not safe kernel pointers. They may be invalid, unmapped, or
fault while being accessed. The copy helpers handle that boundary and let the
driver return `-EFAULT` instead of crashing the kernel.

## Why can kernel code not directly dereference user pointers?

The kernel cannot trust user address space. Direct dereference can create a
security bug or a kernel fault. The safe pattern is to validate through the
kernel's user-copy helpers.

## What is the difference between a mutex and a spinlock?

A mutex can sleep while waiting. A spinlock busy-waits and must be held only
for very short non-sleeping sections. This driver uses a mutex because user
copy and allocation paths can sleep.

## Why are wait queues needed?

They let a process sleep until the device state changes. Empty-buffer readers
wait for data. Full-buffer writers wait for space. Without wait queues, the
driver would either spin or force user space to retry constantly.

## How is O_NONBLOCK handled?

If the operation cannot make progress immediately, `read` or `write` returns
`-EAGAIN` when `O_NONBLOCK` is set. The driver also has a global ioctl mode
that applies non-blocking behavior even if the descriptor was opened normally.

## How does poll work?

The driver registers the caller with `poll_wait`, then reports readiness based
on current buffer state. Stored bytes mean readable. Free capacity means
writable.

## What is ioctl?

`ioctl` is the device-specific control path. Here it handles clear, stats,
capacity changes, mode changes, and stats reset.

## Why must ioctl ABIs be versioned carefully?

Applications compile against ioctl numbers and structure layouts. If those
change casually, old binaries can break. This driver puts an ABI version and
structure size in the stats payload to make compatibility easier to reason
about.

## How are race conditions prevented?

The circular buffer and mode state are protected by a mutex. Counters use
`atomic64_t`. Blocking paths drop the mutex before sleeping and recheck the
condition after waking.

## How is module cleanup handled?

The exit path wakes waiters, removes the device node, destroys the class,
deletes the `cdev`, unregisters the device number, frees the buffer, and frees
the driver context.

## What happens when rmmod is attempted while the device is open?

Because `.owner = THIS_MODULE` is set in `file_operations`, open file
descriptors hold a module reference. A normal `rmmod` fails until those
descriptors are closed.

## How would this design change for PCIe, USB, or platform hardware?

The virtual buffer would not be the whole device anymore. A real driver would
need probe/remove callbacks, hardware register access, interrupt handling, DMA
constraints, and power-management decisions.

## What are the limitations of this virtual driver?

It does not talk to hardware, it has one shared buffer, and it does not preserve
message boundaries. It is useful for practicing the character-device path, not
for modeling a complete hardware driver.

