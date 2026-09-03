# Low-Level Design

## Layering

```text
User-space CLI / Tests
        |
Shared UAPI Header
        |
Linux VFS
        |
file_operations in ringbuf_char.c
        |
Circular Buffer Helpers
        |
Kernel Memory and Wait Queues
```

## Module: `kernel/ringbuf_char.c`

### Responsibility

Own device registration, file operations, ioctl handling, synchronization,
wait queues, statistics, module parameters, logging, and cleanup.

### Main Data Structure

`struct ringbuf_char_dev`

- `devt`: allocated major/minor device number
- `cdev`: VFS character-device object
- `class`: device class
- `device`: published device object
- `buffer`: circular buffer state
- `lock`: mutex protecting shared mutable state
- `read_queue`: wait queue for readers
- `write_queue`: wait queue for writers
- `state_generation`: counter used to wake waiters on control changes
- atomic counters: bytes, calls, failures, blocks, clears, resizes
- `mode`: global behavior flags
- `shutting_down`: unload state

### Public Kernel Entry Points

The functions are public to the VFS through `struct file_operations`, not
exported as symbols:

- `ringbuf_char_open`
- `ringbuf_char_release`
- `ringbuf_char_read`
- `ringbuf_char_write`
- `ringbuf_char_ioctl`
- `ringbuf_char_poll`

### Validation Rules

- Zero-length read/write returns zero.
- Non-blocking empty read returns `-EAGAIN`.
- Non-blocking full write returns `-EAGAIN`.
- Unsupported ioctl returns `-ENOTTY`.
- Bad user-copy returns `-EFAULT`.
- Capacity outside `256..65536` returns `-EINVAL`.
- Capacity below unread data returns `-EMSGSIZE`.

### Failure Conditions

- Kernel memory allocation failure: `-ENOMEM`
- Interrupted mutex acquisition or wait: `-ERESTARTSYS`
- Device shutting down during write: `-ENODEV`
- Invalid ioctl payload: `-EINVAL` or `-EFAULT`

## Module: `kernel/ringbuf_char_buffer.c`

### Responsibility

Own circular-buffer mechanics without knowing about VFS, ioctl, wait queues, or
user pointers.

### Important Functions

- `ringbuf_char_buffer_init`
- `ringbuf_char_buffer_cleanup`
- `ringbuf_char_buffer_stored`
- `ringbuf_char_buffer_available`
- `ringbuf_char_buffer_read_span`
- `ringbuf_char_buffer_consume`
- `ringbuf_char_buffer_write_span`
- `ringbuf_char_buffer_commit`
- `ringbuf_char_buffer_clear`
- `ringbuf_char_buffer_resize`

### Domain Rules

- Capacity must stay within the shared UAPI limits.
- `len` is the number of unread bytes.
- `read_pos` points to the next byte to read.
- `write_pos` points to the next byte to write.
- When `len == 0`, both indexes reset to zero for easier inspection.
- Resize preserves unread bytes in FIFO order.

## Module: `include/ringbuf_char_ioctl.h`

### Responsibility

Define the stable user/kernel ABI.

### ABI Types

`struct ringbuf_char_stats` contains:

- ABI metadata
- capacity and buffer occupancy
- byte counters
- operation counters
- open-handle count
- blocked operation counters
- clear and resize counters
- current mode flags

The structure uses fixed-width Linux integer types and contains no pointers.

## Module: `userspace/client.c`

### Responsibility

Provide a small CLI for manual operation and shell tests.

### Commands

- `write TEXT`
- `fill BYTE COUNT`
- `read BYTES`
- `stats`
- `clear`
- `capacity`
- `resize BYTES`
- `mode normal|nonblock`
- `reset-stats`
- `poll-read TIMEOUT_MS`
- `poll-write TIMEOUT_MS`
- `invalid-ioctl`
- `interactive`

### Error Handling

The client retries interrupted system calls, reports `errno` with
`strerror`, validates numeric input, handles short writes, and closes file
descriptors before returning.

## Module: `userspace/concurrent_test.c`

### Responsibility

Stress concurrent readers and writers without assuming message boundaries.

### Message Format

```text
4 bytes  magic "SCF1"
4 bytes  writer id
4 bytes  sequence number
4 bytes  payload length
4 bytes  checksum
N bytes  deterministic payload
```

Readers reconstruct complete frames from arbitrary read chunks and validate
writer id, sequence number, payload length, checksum, duplicates, and missing
messages.

## Cross-Cutting Concerns

### Authentication and Authorization

There is no application identity model. Access is controlled by Linux device
permissions, module-loading privileges, and process credentials.

### Logging

Module lifecycle and important configuration changes use `pr_info`. Fault
paths use rate-limited warnings. Normal read/write operations do not log.

### Metrics

The ioctl stats structure is the metrics surface. It is intentionally small and
safe to read from user space.

### Rate Limiting

The driver does not rate-limit callers. Linux permissions and test tooling are
the current control points. A future daemon or sysfs policy layer could add
rate limits if the device became shared on a multi-user system.

