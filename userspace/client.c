// SPDX-License-Identifier: GPL-2.0-only
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <unistd.h>

#include "ringbuf_char_ioctl.h"

#ifndef O_CLOEXEC
#define O_CLOEXEC 0
#endif

#define CLIENT_MAX_IO_BYTES (1024UL * 1024UL)
#define INTERACTIVE_MAX_ARGS 16
#define INTERACTIVE_LINE_SIZE 4096

struct cli_options {
	const char *device_path;
	bool nonblock;
};

static bool is_again_error(int err)
{
	if (err == EAGAIN)
		return true;
#if EWOULDBLOCK != EAGAIN
	return err == EWOULDBLOCK;
#else
	return false;
#endif
}

static void print_errno(const char *operation, int err)
{
	fprintf(stderr, "%s failed: %s (errno=%d)\n", operation, strerror(err),
		err);
}

static int close_checked(int fd)
{
	if (close(fd) == -1) {
		print_errno("close", errno);
		return 1;
	}

	return 0;
}

static void usage(FILE *stream, const char *program)
{
	fprintf(stream,
		"Usage: %s [--device PATH] [--nonblock|-n] COMMAND [ARGS]\n"
		"\n"
		"Commands:\n"
		"  write TEXT              Write TEXT to the device\n"
		"  fill BYTE COUNT         Write COUNT copies of BYTE\n"
		"  read BYTES              Read up to BYTES and write raw data to stdout\n"
		"  stats                   Print driver statistics\n"
		"  clear                   Clear buffered data\n"
		"  capacity                Print current capacity\n"
		"  resize BYTES            Resize logical buffer capacity\n"
		"  mode normal|nonblock    Configure global driver mode\n"
		"  reset-stats             Reset operational counters\n"
		"  poll-read TIMEOUT_MS    Wait for readable readiness\n"
		"  poll-write TIMEOUT_MS   Wait for writable readiness\n"
		"  invalid-ioctl           Send an unsupported ioctl for tests\n"
		"  interactive             Start a simple command loop\n",
		program);
}

static int parse_u64(const char *text, uint64_t min_value, uint64_t max_value,
		     uint64_t *out)
{
	unsigned long long value;
	char *end = NULL;

	if (!text || !*text || text[0] == '-')
		return -EINVAL;

	errno = 0;
	value = strtoull(text, &end, 10);
	if (errno == ERANGE || end == text || *end != '\0')
		return -EINVAL;

	if (value < min_value || value > max_value)
		return -ERANGE;

	*out = (uint64_t)value;
	return 0;
}

static int parse_size_arg(const char *text, size_t min_value, size_t max_value,
			  size_t *out)
{
	uint64_t parsed;
	int ret;

	ret = parse_u64(text, min_value, max_value, &parsed);
	if (ret)
		return ret;

	*out = (size_t)parsed;
	return 0;
}

static int parse_int_arg(const char *text, int min_value, int max_value,
			 int *out)
{
	uint64_t parsed;
	int ret;

	ret = parse_u64(text, (uint64_t)min_value, (uint64_t)max_value,
			&parsed);
	if (ret)
		return ret;

	*out = (int)parsed;
	return 0;
}

static int open_device(const struct cli_options *opts, int flags)
{
	int fd;
	int open_flags = flags | O_CLOEXEC;

	if (opts->nonblock)
		open_flags |= O_NONBLOCK;

	do {
		fd = open(opts->device_path, open_flags);
	} while (fd == -1 && errno == EINTR);

	if (fd == -1)
		print_errno(opts->device_path, errno);

	return fd;
}

static int ioctl_retry(int fd, unsigned long request, void *arg)
{
	int ret;

	do {
		ret = ioctl(fd, request, arg);
	} while (ret == -1 && errno == EINTR);

	return ret;
}

static ssize_t read_retry(int fd, void *buffer, size_t count)
{
	ssize_t ret;

	do {
		ret = read(fd, buffer, count);
	} while (ret == -1 && errno == EINTR);

	return ret;
}

static ssize_t write_retry(int fd, const void *buffer, size_t count)
{
	ssize_t ret;

	do {
		ret = write(fd, buffer, count);
	} while (ret == -1 && errno == EINTR);

	return ret;
}

static int write_all(int fd, const unsigned char *data, size_t len,
		     size_t *bytes_written, int *error_out)
{
	size_t offset = 0;

	while (offset < len) {
		ssize_t ret = write_retry(fd, data + offset, len - offset);

		if (ret == -1) {
			*bytes_written = offset;
			*error_out = errno;
			return -1;
		}

		if (ret == 0) {
			*bytes_written = offset;
			*error_out = EIO;
			return -1;
		}

		offset += (size_t)ret;
	}

	*bytes_written = offset;
	*error_out = 0;
	return 0;
}

static int command_write(const struct cli_options *opts, const char *text)
{
	int fd;
	size_t written = 0;
	int err = 0;
	int rc = 0;

	fd = open_device(opts, O_WRONLY);
	if (fd == -1)
		return 1;

	if (write_all(fd, (const unsigned char *)text, strlen(text), &written,
		      &err) == -1) {
		if (is_again_error(err))
			fprintf(stderr,
				"write stopped after %zu bytes: %s (errno=%d)\n",
				written, strerror(err), err);
		else
			print_errno("write", err);
		rc = 1;
	} else {
		printf("wrote %zu bytes\n", written);
	}

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static int parse_byte_arg(const char *text, unsigned char *byte)
{
	uint64_t parsed;

	if (strlen(text) == 1) {
		*byte = (unsigned char)text[0];
		return 0;
	}

	if (parse_u64(text, 0, 255, &parsed))
		return -EINVAL;

	*byte = (unsigned char)parsed;
	return 0;
}

static int command_fill(const struct cli_options *opts, const char *byte_text,
			const char *count_text)
{
	unsigned char byte;
	unsigned char chunk[4096];
	size_t remaining;
	size_t total;
	size_t written_total = 0;
	int fd;
	int rc = 0;

	if (parse_byte_arg(byte_text, &byte)) {
		fprintf(stderr, "invalid BYTE: %s\n", byte_text);
		return 1;
	}

	if (parse_size_arg(count_text, 0, CLIENT_MAX_IO_BYTES, &total)) {
		fprintf(stderr, "invalid COUNT: %s\n", count_text);
		return 1;
	}

	memset(chunk, byte, sizeof(chunk));
	fd = open_device(opts, O_WRONLY);
	if (fd == -1)
		return 1;

	remaining = total;
	while (remaining > 0) {
		size_t request = remaining < sizeof(chunk) ? remaining :
				 sizeof(chunk);
		size_t wrote = 0;
		int err = 0;

		if (write_all(fd, chunk, request, &wrote, &err) == -1) {
			written_total += wrote;
			print_errno("write", err);
			rc = 1;
			break;
		}

		written_total += wrote;
		remaining -= wrote;
	}

	if (rc == 0)
		printf("wrote %zu bytes\n", written_total);

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static int command_read(const struct cli_options *opts, const char *count_text)
{
	unsigned char stack_byte;
	unsigned char *buffer = &stack_byte;
	size_t count;
	ssize_t ret;
	int fd;
	int rc = 0;

	if (parse_size_arg(count_text, 0, CLIENT_MAX_IO_BYTES, &count)) {
		fprintf(stderr, "invalid BYTES: %s\n", count_text);
		return 1;
	}

	if (count > 0) {
		buffer = malloc(count);
		if (!buffer) {
			print_errno("malloc", ENOMEM);
			return 1;
		}
	}

	fd = open_device(opts, O_RDONLY);
	if (fd == -1) {
		free(count > 0 ? buffer : NULL);
		return 1;
	}

	ret = read_retry(fd, buffer, count);
	if (ret == -1) {
		print_errno("read", errno);
		rc = 1;
	} else if (ret > 0) {
		size_t written = fwrite(buffer, 1, (size_t)ret, stdout);

		if (written != (size_t)ret) {
			print_errno("fwrite", ferror(stdout) ? errno : EIO);
			rc = 1;
		}
	}

	if (close_checked(fd))
		rc = 1;

	free(count > 0 ? buffer : NULL);
	return rc;
}

static int command_clear(const struct cli_options *opts)
{
	int fd = open_device(opts, O_RDWR);
	int rc = 0;

	if (fd == -1)
		return 1;

	if (ioctl_retry(fd, RINGBUF_CHAR_IOC_CLEAR, NULL) == -1) {
		print_errno("ioctl CLEAR", errno);
		rc = 1;
	} else {
		puts("cleared");
	}

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static int command_capacity(const struct cli_options *opts)
{
	__u64 capacity = 0;
	int fd = open_device(opts, O_RDWR);
	int rc = 0;

	if (fd == -1)
		return 1;

	if (ioctl_retry(fd, RINGBUF_CHAR_IOC_GET_CAPACITY, &capacity) == -1) {
		print_errno("ioctl GET_CAPACITY", errno);
		rc = 1;
	} else {
		printf("%" PRIu64 "\n", (uint64_t)capacity);
	}

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static int command_resize(const struct cli_options *opts, const char *text)
{
	uint64_t parsed;
	__u64 capacity;
	int fd;
	int rc = 0;

	if (parse_u64(text, 0, UINT64_MAX, &parsed)) {
		fprintf(stderr, "invalid capacity: %s\n", text);
		return 1;
	}

	capacity = (__u64)parsed;
	fd = open_device(opts, O_RDWR);
	if (fd == -1)
		return 1;

	if (ioctl_retry(fd, RINGBUF_CHAR_IOC_SET_CAPACITY, &capacity) == -1) {
		print_errno("ioctl SET_CAPACITY", errno);
		rc = 1;
	} else {
		printf("%" PRIu64 "\n", parsed);
	}

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static void print_stats(const struct ringbuf_char_stats *stats)
{
	printf("abi_version: %u\n", stats->abi_version);
	printf("struct_size: %u\n", stats->struct_size);
	printf("capacity: %" PRIu64 "\n", (uint64_t)stats->current_capacity);
	printf("stored_bytes: %" PRIu64 "\n", (uint64_t)stats->stored_bytes);
	printf("available_bytes: %" PRIu64 "\n",
	       (uint64_t)stats->available_bytes);
	printf("total_bytes_read: %" PRIu64 "\n",
	       (uint64_t)stats->total_bytes_read);
	printf("total_bytes_written: %" PRIu64 "\n",
	       (uint64_t)stats->total_bytes_written);
	printf("read_calls: %" PRIu64 "\n", (uint64_t)stats->read_calls);
	printf("write_calls: %" PRIu64 "\n", (uint64_t)stats->write_calls);
	printf("open_calls: %" PRIu64 "\n", (uint64_t)stats->open_calls);
	printf("current_open_handles: %" PRIu64 "\n",
	       (uint64_t)stats->current_open_handles);
	printf("ioctl_calls: %" PRIu64 "\n", (uint64_t)stats->ioctl_calls);
	printf("failed_operations: %" PRIu64 "\n",
	       (uint64_t)stats->failed_operations);
	printf("blocked_reads: %" PRIu64 "\n", (uint64_t)stats->blocked_reads);
	printf("blocked_writes: %" PRIu64 "\n",
	       (uint64_t)stats->blocked_writes);
	printf("clears: %" PRIu64 "\n", (uint64_t)stats->clears);
	printf("resizes: %" PRIu64 "\n", (uint64_t)stats->resizes);
	printf("mode: 0x%08x\n", stats->mode);
}

static int command_stats(const struct cli_options *opts)
{
	struct ringbuf_char_stats stats;
	int fd = open_device(opts, O_RDWR);
	int rc = 0;

	if (fd == -1)
		return 1;

	memset(&stats, 0, sizeof(stats));
	if (ioctl_retry(fd, RINGBUF_CHAR_IOC_GET_STATS, &stats) == -1) {
		print_errno("ioctl GET_STATS", errno);
		rc = 1;
	} else if (stats.abi_version != RINGBUF_CHAR_ABI_VERSION ||
		   stats.struct_size != sizeof(stats)) {
		fprintf(stderr,
			"unexpected stats ABI: version=%u size=%u expected version=%u size=%zu\n",
			stats.abi_version, stats.struct_size,
			RINGBUF_CHAR_ABI_VERSION, sizeof(stats));
		rc = 1;
	} else {
		print_stats(&stats);
	}

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static int command_reset_stats(const struct cli_options *opts)
{
	int fd = open_device(opts, O_RDWR);
	int rc = 0;

	if (fd == -1)
		return 1;

	if (ioctl_retry(fd, RINGBUF_CHAR_IOC_RESET_STATS, NULL) == -1) {
		print_errno("ioctl RESET_STATS", errno);
		rc = 1;
	} else {
		puts("statistics reset");
	}

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static int command_mode(const struct cli_options *opts, const char *mode_text)
{
	__u32 mode;
	int fd;
	int rc = 0;

	if (strcmp(mode_text, "normal") == 0) {
		mode = 0;
	} else if (strcmp(mode_text, "nonblock") == 0) {
		mode = RINGBUF_CHAR_MODE_F_NONBLOCK;
	} else {
		fprintf(stderr, "mode must be 'normal' or 'nonblock'\n");
		return 1;
	}

	fd = open_device(opts, O_RDWR);
	if (fd == -1)
		return 1;

	if (ioctl_retry(fd, RINGBUF_CHAR_IOC_SET_MODE, &mode) == -1) {
		print_errno("ioctl SET_MODE", errno);
		rc = 1;
	} else {
		printf("mode: 0x%08x\n", mode);
	}

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static int poll_once(int fd, short events, int timeout_ms)
{
	struct pollfd pfd;
	int ret;

	pfd.fd = fd;
	pfd.events = events;
	pfd.revents = 0;

	do {
		ret = poll(&pfd, 1, timeout_ms);
	} while (ret == -1 && errno == EINTR);

	if (ret == -1)
		return -1;
	if (ret == 0)
		return 0;
	if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) {
		errno = EIO;
		return -1;
	}
	if (pfd.revents & events)
		return 1;

	return 0;
}

static int command_poll(const struct cli_options *opts, const char *timeout_text,
			bool want_read)
{
	int timeout_ms;
	int fd;
	int ret;
	int rc = 0;

	if (parse_int_arg(timeout_text, 0, INT_MAX, &timeout_ms)) {
		fprintf(stderr, "invalid timeout: %s\n", timeout_text);
		return 1;
	}

	fd = open_device(opts, want_read ? O_RDONLY : O_WRONLY);
	if (fd == -1)
		return 1;

	ret = poll_once(fd, want_read ? POLLIN : POLLOUT, timeout_ms);
	if (ret == -1) {
		print_errno("poll", errno);
		rc = 1;
	} else if (ret == 0) {
		puts("timeout");
	} else {
		puts(want_read ? "readable" : "writable");
	}

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static int command_invalid_ioctl(const struct cli_options *opts)
{
	int fd = open_device(opts, O_RDWR);
	int rc = 1;

	if (fd == -1)
		return 1;

	if (ioctl_retry(fd, _IO('Z', 0x7f), NULL) == -1) {
		print_errno("ioctl INVALID", errno);
		rc = 2;
	} else {
		fprintf(stderr, "invalid ioctl unexpectedly succeeded\n");
		rc = 1;
	}

	if (close_checked(fd))
		rc = 1;

	return rc;
}

static int dispatch_command(const char *program, const struct cli_options *opts,
			    int argc, char **argv);

static int split_interactive_line(char *line, char **argv, size_t max_args)
{
	size_t argc = 0;
	char *p = line;

	while (*p != '\0') {
		while (*p == ' ' || *p == '\t' || *p == '\n')
			p++;
		if (*p == '\0')
			break;
		if (argc == max_args)
			return -1;

		if (*p == '"') {
			p++;
			argv[argc++] = p;
			while (*p != '\0' && *p != '"')
				p++;
			if (*p == '"')
				*p++ = '\0';
		} else {
			argv[argc++] = p;
			while (*p != '\0' && *p != ' ' && *p != '\t' &&
			       *p != '\n')
				p++;
			if (*p != '\0')
				*p++ = '\0';
		}
	}

	return (int)argc;
}

static int command_interactive(const char *program, const struct cli_options *opts)
{
	char line[INTERACTIVE_LINE_SIZE];

	puts("ringbuf_char interactive mode. Type 'help' or 'quit'.");
	for (;;) {
		char *argv[INTERACTIVE_MAX_ARGS];
		int argc;
		int rc;

		fputs("ringbuf_char> ", stdout);
		fflush(stdout);

		if (!fgets(line, sizeof(line), stdin)) {
			putchar('\n');
			break;
		}

		argc = split_interactive_line(line, argv, INTERACTIVE_MAX_ARGS);
		if (argc < 0) {
			fprintf(stderr, "too many arguments\n");
			continue;
		}
		if (argc == 0)
			continue;
		if (strcmp(argv[0], "quit") == 0 || strcmp(argv[0], "exit") == 0)
			break;

		rc = dispatch_command(program, opts, argc, argv);
		if (rc != 0)
			fprintf(stderr, "command exited with status %d\n", rc);
	}

	return 0;
}

static int dispatch_command(const char *program, const struct cli_options *opts,
			    int argc, char **argv)
{
	const char *command;

	if (argc < 1) {
		usage(stderr, program);
		return 1;
	}

	command = argv[0];
	if (strcmp(command, "help") == 0 || strcmp(command, "--help") == 0 ||
	    strcmp(command, "-h") == 0) {
		usage(stdout, program);
		return 0;
	}
	if (strcmp(command, "write") == 0) {
		if (argc != 2) {
			fprintf(stderr, "write requires TEXT\n");
			return 1;
		}
		return command_write(opts, argv[1]);
	}
	if (strcmp(command, "fill") == 0) {
		if (argc != 3) {
			fprintf(stderr, "fill requires BYTE and COUNT\n");
			return 1;
		}
		return command_fill(opts, argv[1], argv[2]);
	}
	if (strcmp(command, "read") == 0) {
		if (argc != 2) {
			fprintf(stderr, "read requires BYTES\n");
			return 1;
		}
		return command_read(opts, argv[1]);
	}
	if (strcmp(command, "stats") == 0)
		return command_stats(opts);
	if (strcmp(command, "clear") == 0)
		return command_clear(opts);
	if (strcmp(command, "capacity") == 0)
		return command_capacity(opts);
	if (strcmp(command, "resize") == 0) {
		if (argc != 2) {
			fprintf(stderr, "resize requires BYTES\n");
			return 1;
		}
		return command_resize(opts, argv[1]);
	}
	if (strcmp(command, "mode") == 0) {
		if (argc != 2) {
			fprintf(stderr, "mode requires normal or nonblock\n");
			return 1;
		}
		return command_mode(opts, argv[1]);
	}
	if (strcmp(command, "reset-stats") == 0)
		return command_reset_stats(opts);
	if (strcmp(command, "poll-read") == 0) {
		if (argc != 2) {
			fprintf(stderr, "poll-read requires TIMEOUT_MS\n");
			return 1;
		}
		return command_poll(opts, argv[1], true);
	}
	if (strcmp(command, "poll-write") == 0) {
		if (argc != 2) {
			fprintf(stderr, "poll-write requires TIMEOUT_MS\n");
			return 1;
		}
		return command_poll(opts, argv[1], false);
	}
	if (strcmp(command, "invalid-ioctl") == 0)
		return command_invalid_ioctl(opts);
	if (strcmp(command, "interactive") == 0)
		return command_interactive(program, opts);

	fprintf(stderr, "unknown command: %s\n", command);
	usage(stderr, program);
	return 1;
}

int main(int argc, char **argv)
{
	struct cli_options opts = {
		.device_path = RINGBUF_CHAR_DEVICE_PATH,
		.nonblock = false,
	};
	int index = 1;

	while (index < argc) {
		if (strcmp(argv[index], "--device") == 0) {
			if (index + 1 >= argc) {
				fprintf(stderr, "--device requires PATH\n");
				return 1;
			}
			opts.device_path = argv[index + 1];
			index += 2;
		} else if (strcmp(argv[index], "--nonblock") == 0 ||
			   strcmp(argv[index], "-n") == 0) {
			opts.nonblock = true;
			index++;
		} else {
			break;
		}
	}

	if (index >= argc) {
		usage(stderr, argv[0]);
		return 1;
	}

	return dispatch_command(argv[0], &opts, argc - index, &argv[index]);
}
