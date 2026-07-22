# Architecture

## Device Registration

`shivam_char` is an out-of-tree Linux kernel module. During module
initialization it validates the `buffer_capacity` module parameter, allocates
the circular buffer, obtains a dynamic device number with
`alloc_chrdev_region`, initializes `struct cdev`, calls `cdev_add`, creates a
device class, and publishes `/dev/shivam_char` through `device_create`.

The module does not hardcode a major number. Dynamic allocation avoids
colliding with devices already registered by the running kernel.

## VFS Dispatch

User processes interact with `/dev/shivam_char` using normal file-descriptor
operations. The VFS resolves those operations to the driver's
`struct file_operations` table:

- `open` stores the driver context in `file->private_data`.
- `release` decrements the current open-handle count.
- `read` copies bytes from the circular buffer to user space.
- `write` copies bytes from user space into the circular buffer.
- `unlocked_ioctl` handles the control-plane ABI.
- `poll` reports readiness to `poll`, `select`, and `epoll`.
- `llseek` is `no_llseek` because the device is a stream.

## Circular Buffer

The buffer tracks an allocated byte array, total capacity, stored byte count,
read index, and write index. Reads and writes operate on contiguous spans and
then consume or commit those spans. This avoids large temporary allocations and
handles wraparound explicitly.

Resize preserves unread data in FIFO order. A resize smaller than the unread
byte count fails with `-EMSGSIZE`. Invalid capacities fail with `-EINVAL`.

## Locking

The driver uses one mutex around shared mutable device state: buffer metadata,
buffer contents, mode, and shutdown state. Statistics that are frequently
updated use `atomic64_t`, while capacity and stored-byte snapshots are read
under the mutex for ioctl stats.

The driver never waits on a wait queue while holding the mutex. Blocking paths
check the condition, drop the mutex, sleep with `wait_event_interruptible`, and
then reacquire and recheck.

## Wait Queues

Readers sleep on `read_queue` when the buffer is empty and blocking behavior is
enabled. Writers sleep on `write_queue` when the buffer is full. Successful
writes wake readers. Successful reads, clears, and resizes wake writers.

A state-generation counter lets control-plane operations such as clear, resize,
and mode changes wake blocked readers or writers even when the byte count alone
does not change in their favor.

## Poll

`poll_wait` registers the caller on both wait queues. The driver reports:

- `POLLIN | POLLRDNORM` when stored bytes are available.
- `POLLOUT | POLLWRNORM` when at least one byte of capacity is free.

This supports `poll`, `select`, and `epoll` through the standard VFS path.

## IOCTL

The ABI is declared in `include/shivam_char_ioctl.h`, which is shared by the
module and user-space tools. The statistics structure includes an ABI version
and structure size so user space can detect incompatible changes.

The driver validates ioctl magic and command numbers. Unsupported commands
return `-ENOTTY`.

## Lifecycle and Cleanup

Initialization uses structured `goto` cleanup labels so partial setup is
unwound in reverse order. Module removal wakes waiters, destroys the device
node and class, deletes the `cdev`, unregisters the device number, frees the
circular buffer, and releases the driver context. Normal module ownership
prevents `rmmod` while file descriptors are open.

