# Architecture

This note describes how the driver is wired together. It is written from the
code outward, because that is usually how I debug kernel projects: start with
what the module registers, then follow one system call at a time.

## Device Registration

`shivam_char` is an out-of-tree module. On load, it:

- validates the `buffer_capacity` module parameter
- allocates the circular buffer
- asks the kernel for a device number with `alloc_chrdev_region`
- initializes and registers a `struct cdev`
- creates a class and device node for `/dev/shivam_char`

The driver does not use a hardcoded major number. The running kernel may
already have that number assigned to something else, so dynamic allocation is
the safer default.

## VFS Dispatch

Once `/dev/shivam_char` exists, normal system calls reach the driver through
the VFS. The module fills a `struct file_operations` table with these handlers:

- `open` saves the driver context in `file->private_data`.
- `release` drops the open-handle count.
- `read` drains bytes from the circular buffer.
- `write` appends bytes into the circular buffer.
- `unlocked_ioctl` handles clear, stats, capacity, mode, and reset commands.
- `poll` reports readable and writable readiness.
- `llseek` is `no_llseek`, because this device is a stream.

There is only one device instance, so one central driver context is enough.

## Circular Buffer

The buffer keeps five pieces of state: data pointer, capacity, stored byte
count, read index, and write index. The read/write helpers expose contiguous
spans so the driver can copy directly to or from user space without allocating
a large temporary buffer for every operation.

Resize is intentionally conservative. If the new capacity can hold all unread
bytes, the old circular contents are linearized into the new allocation. If the
caller asks for a capacity smaller than the unread data, resize fails with
`-EMSGSIZE`.

## Locking

Buffer contents, buffer metadata, mode, and shutdown state are protected by one
mutex. The high-frequency counters are `atomic64_t`, which keeps simple stats
updates out of the main lock path.

The blocking paths use the usual pattern:

1. take the mutex
2. check whether the operation can continue
3. drop the mutex before sleeping
4. wait with `wait_event_interruptible`
5. take the mutex again and recheck

That recheck matters. A wakeup only means "look again", not "the condition is
guaranteed forever."

## Wait Queues

Empty-buffer readers wait on `read_queue`. Full-buffer writers wait on
`write_queue`.

Successful writes wake readers. Successful reads wake writers. Clear, resize,
and mode changes wake both sides because they change the state a blocked
process may care about.

The driver also keeps a small state-generation counter. That gives blocked
readers a way to notice control-plane changes such as clear or mode change even
when no new data was written.

## Poll

`poll_wait` registers the caller on both wait queues. Then the driver checks
the current buffer state:

- stored bytes mean `POLLIN | POLLRDNORM`
- free space means `POLLOUT | POLLWRNORM`

That is enough for `poll`, `select`, and `epoll` users because they all come
through the same file operation.

## IOCTL

The ABI is in `include/shivam_char_ioctl.h`. The stats structure includes both
`abi_version` and `struct_size`; that is a small amount of discipline up front
that makes future changes less messy.

Unsupported ioctl commands return `-ENOTTY`. Bad user pointers return
`-EFAULT`. Invalid capacities return `-EINVAL` or `-EMSGSIZE`, depending on
whether the value is out of range or too small for the unread data.

## Lifecycle and Cleanup

Initialization unwinds in reverse order with `goto` labels. On unload, the
module wakes waiters, destroys the device node, destroys the class, deletes the
`cdev`, unregisters the device number, frees the buffer, and frees the driver
context.

If a process still has the device open, normal module ownership keeps `rmmod`
from removing it.

