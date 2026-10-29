# Validation foundation

## Available checks

```sh
bash scripts/check_shell.sh
bash tests/test_shell_checker.sh
make -C userspace test
make userspace
make module
sudo bash tests/run_all_tests.sh
```

The startup test uses linker wrappers to fail each of four pthread creation
positions. No worker executes and no device is opened. Every successfully
created synthetic handle must be joined exactly once; joining an uncreated
handle fails the test. This tests the cleanup contract, not pthread scheduling.

The shell regression passes a valid first script and invalid second script to
the checker. It prevents a return to invoking bash -n with multiple script
arguments, which checks only the first script.

## KUnit buffer suite

Boot a disposable kernel configured with CONFIG_KUNIT=y (or m), with matching
build headers. Build the optional standalone test module:

```sh
make kunit
sudo modprobe kunit # only needed when CONFIG_KUNIT=m
sudo insmod ringbuf_char_test.ko
sudo dmesg
sudo rmmod ringbuf_char_test
```

Inspect the KTAP result for the ringbuf-char-buffer suite. Module insertion
alone is not a passing result. The test module does not register a device and
does not require loading ringbuf_char. It uses the actual buffer implementation.
Tests cover empty/full, wraparound, wrapped FIFO resize, shrink-to-full, invalid
capacity, rejected shrink preserving data/allocation, and clear.

Allocation-failure injection and KASAN/lockdep runs remain outstanding. The
ordinary distro-header CI does not claim to execute KUnit.

## Evidence status: 2026-10-10

Passed locally: every shell script parsed by the shared checker; the invalid
second-script regression; git diff --check; C11 strict syntax checking of
thread_start_test.c with Windows UCRT GCC (exit 0 after adding its runtime bin
directory to PATH). Linux compilation, linking, and execution remain unverified.

The Windows host has no installed WSL distributions reported by wsl --list
--quiet. Linux driver execution, KUnit, and the thread-wrapper executable are
not yet validated here. CI configuration is not evidence of a successful CI run.
Record commit, dirty-tree diff, kernel release/config, compiler, commands, exit
codes, full KTAP output, and kernel logs with each Linux validation run.

Stats are approximate during active I/O. Global control semantics and reset
limitations are documented in api/API_SPECIFICATION.md. Exact interval counters
would require a separate design change.
