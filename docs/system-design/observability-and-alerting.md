# Observability and Alerting

## Current Observability

- `dmesg` messages prefixed with `ringbuf_char:`
- ioctl statistics through `ringbuf_char_client stats`
- integration-test logs under `tests/logs/`
- load/unload/inspect scripts that print module and device state

## Useful Local Dashboard

For a local VM, a simple terminal dashboard is enough:

```text
capacity
stored_bytes
available_bytes
total_bytes_read
total_bytes_written
read_calls
write_calls
blocked_reads
blocked_writes
failed_operations
clears
resizes
```

## Future Fleet Dashboards

If this becomes a managed driver deployed to several hosts, useful dashboards
would include:

- module loaded/unloaded count by host
- load failures by kernel version
- read/write throughput by host
- failed operations per minute
- blocked reads/writes
- capacity changes
- suspicious ioctl attempts
- kernel warnings after test runs

## Alerts

Avoid alerts for normal local development noise. Useful alerts in a managed
environment would be:

- module load failure after deployment
- repeated `failed_operations` increase
- kernel warnings or oops after module load
- test timeout during CI/VM validation
- device node missing after successful `insmod`
- module busy during planned unload

## Tracing Roadmap

Future versions could add tracepoints around:

- read wait begin/end
- write wait begin/end
- buffer resize
- clear
- copy fault
- poll readiness

