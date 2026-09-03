# API and ABI Specification

This project does not expose an HTTP API. The public interface is the Linux
device file `/dev/ringbuf_char`, plus ioctl commands defined in
`include/ringbuf_char_ioctl.h`.

## Versioning Strategy

The current ABI version is:

```text
RINGBUF_CHAR_ABI_VERSION = 1
```

Future breaking changes should:

- add a new ABI version
- avoid reusing ioctl command numbers with different semantics
- keep old structures supported when practical
- document migration steps

## Device Path

```text
/dev/ringbuf_char
```

## Standard Error Behavior

| Error | Meaning |
| --- | --- |
| `EAGAIN` | operation would block on a non-blocking descriptor |
| `EINVAL` | invalid argument or unsupported mode/capacity value |
| `EFAULT` | invalid user pointer |
| `ENOMEM` | allocation failed |
| `ERESTARTSYS` | interrupted blocking wait inside the kernel |
| `ENOTTY` | unsupported ioctl |
| `EMSGSIZE` | resize is smaller than unread buffered data |

No kernel stack traces, pointers, or sensitive memory are exposed through the
ABI.

## File Operations

### `open`

Authentication: Linux file permissions.

Behavior:

- stores driver context in `file->private_data`
- increments open counters
- returns `0` on success

### `release`

Behavior:

- decrements open-handle count
- returns `0`

### `read`

Request:

```c
ssize_t read(int fd, void *buf, size_t count);
```

Behavior:

- returns `0` for zero-length reads
- returns up to `count` bytes when data exists
- blocks when empty unless non-blocking mode is active
- returns `-EAGAIN` when empty and non-blocking

### `write`

Request:

```c
ssize_t write(int fd, const void *buf, size_t count);
```

Behavior:

- returns `0` for zero-length writes
- writes as much as currently fits
- may return a partial byte count
- blocks when full unless non-blocking mode is active
- returns `-EAGAIN` when full and non-blocking

### `poll`

Readable flags:

```text
POLLIN | POLLRDNORM
```

Writable flags:

```text
POLLOUT | POLLWRNORM
```

## Ioctl Commands

### `RINGBUF_CHAR_IOC_CLEAR`

Direction: none.

Effect:

- clears buffered data
- resets read/write indexes
- wakes readers and writers

### `RINGBUF_CHAR_IOC_GET_STATS`

Direction: kernel to user.

Payload:

```c
struct ringbuf_char_stats
```

Returns a fixed-size snapshot of counters and buffer state.

### `RINGBUF_CHAR_IOC_SET_CAPACITY`

Direction: user to kernel.

Payload:

```c
__u64 capacity;
```

Validation:

- must be between 256 and 65536
- must be large enough to hold unread bytes

### `RINGBUF_CHAR_IOC_GET_CAPACITY`

Direction: kernel to user.

Payload:

```c
__u64 capacity;
```

### `RINGBUF_CHAR_IOC_SET_MODE`

Direction: user to kernel.

Payload:

```c
__u32 mode;
```

Allowed flags:

```text
RINGBUF_CHAR_MODE_F_NONBLOCK
```

### `RINGBUF_CHAR_IOC_RESET_STATS`

Direction: none.

Effect:

- resets operational counters
- does not clear buffered data
- does not reset current open-handle count

## CLI Contract

The user-space client wraps the ABI:

```text
ringbuf_char_client write TEXT
ringbuf_char_client fill BYTE COUNT
ringbuf_char_client read BYTES
ringbuf_char_client stats
ringbuf_char_client clear
ringbuf_char_client capacity
ringbuf_char_client resize BYTES
ringbuf_char_client mode normal|nonblock
ringbuf_char_client reset-stats
ringbuf_char_client poll-read TIMEOUT_MS
ringbuf_char_client poll-write TIMEOUT_MS
```

Exit code `0` means success. Non-zero means the command failed and printed a
human-readable error to stderr.

