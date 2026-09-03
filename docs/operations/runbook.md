# Operations Runbook

## First-Time Setup

```sh
bash scripts/setup.sh
sudo bash scripts/setup.sh --install --yes
```

## Build

```sh
make
```

## Load

```sh
sudo bash scripts/load.sh
```

With parameters:

```sh
sudo bash scripts/load.sh buffer_capacity=8192 debug=1
```

## Inspect

```sh
sudo bash scripts/inspect.sh
userspace/ringbuf_char_client stats
dmesg | grep 'ringbuf_char:'
```

## Run Tests

```sh
sudo bash tests/run_all_tests.sh
```

## Unload

```sh
sudo bash scripts/unload.sh
```

## Module Busy

```sh
sudo fuser -v /dev/ringbuf_char
sudo bash scripts/unload.sh
```

Close the listed processes before retrying.

## Bad Test Run

1. Save `tests/logs`.
2. Save recent `dmesg`.
3. Unload the module.
4. Reboot or restore the VM snapshot if the kernel reported an oops.
5. Rerun a single failing test with `debug=1`.

## Demo Script

```sh
make
sudo bash scripts/reload.sh buffer_capacity=4096
userspace/ringbuf_char_client clear
userspace/ringbuf_char_client write "hello from the driver"
userspace/ringbuf_char_client read 21
userspace/ringbuf_char_client stats
userspace/concurrent_test --writers 4 --readers 4 --messages 250 --size 64
sudo bash scripts/unload.sh
```

