// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include "ringbuf_char_ioctl.h"

#define CHECK(expr) do { if (!(expr)) { \
	fprintf(stderr, "FAIL line %d: %s (errno=%d)\n", __LINE__, #expr, errno); \
	exit(EXIT_FAILURE); } } while (0)

static int reader_fd;
static ssize_t reader_result;
static int reader_errno;
static char reader_byte;
static int writer_fd;
static ssize_t writer_result;
static int writer_errno;

static void *blocked_writer(void *unused)
{
	(void)unused;
	writer_result = write(writer_fd, "W", 1);
	writer_errno = errno;
	return NULL;
}

static void *blocked_reader(void *unused)
{
	(void)unused;
	reader_result = read(reader_fd, &reader_byte, 1);
	reader_errno = errno;
	return NULL;
}

static void wait_for_block(int fd, __u64 previous)
{
	struct timespec pause = { .tv_nsec = 1000000 };
	struct ringbuf_char_stats stats;
	unsigned int i;

	for (i = 0; i < 3000; i++) {
		CHECK(ioctl(fd, RINGBUF_CHAR_IOC_GET_STATS, &stats) == 0);
		if (stats.blocked_reads > previous)
			return;
		nanosleep(&pause, NULL);
	}
	fprintf(stderr, "FAIL: reader did not enter wait queue\n");
	exit(EXIT_FAILURE);
}

static void control_wakeup(int fd, unsigned int command, int nonblock)
{
	struct ringbuf_char_stats stats;
	pthread_t thread;
	__u64 capacity = 512;
	__u32 mode = nonblock ? RINGBUF_CHAR_MODE_F_NONBLOCK : 0;

	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_CLEAR) == 0);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_GET_STATS, &stats) == 0);
	CHECK(pthread_create(&thread, NULL, blocked_reader, NULL) == 0);
	wait_for_block(fd, stats.blocked_reads);
	if (command == RINGBUF_CHAR_IOC_SET_CAPACITY)
		CHECK(ioctl(fd, command, &capacity) == 0);
	else if (command == RINGBUF_CHAR_IOC_SET_MODE)
		CHECK(ioctl(fd, command, &mode) == 0);
	else
		CHECK(ioctl(fd, command) == 0);
	if (!nonblock) {
		/* A control wakeup must requeue, never synthesize EOF. */
		wait_for_block(fd, stats.blocked_reads + 1);
		CHECK(write(fd, "K", 1) == 1);
	}
	CHECK(pthread_join(thread, NULL) == 0);
	if (nonblock) {
		CHECK(reader_result == -1 && reader_errno == EAGAIN);
		mode = 0;
		CHECK(ioctl(fd, RINGBUF_CHAR_IOC_SET_MODE, &mode) == 0);
	} else {
		CHECK(reader_result == 1 && reader_byte == 'K');
	}
}

static void interrupt_handler(int signal_number)
{
	(void)signal_number;
}

static void interrupted_read(int fd)
{
	struct sigaction action = { .sa_handler = interrupt_handler };
	struct sigaction previous;
	struct ringbuf_char_stats stats;
	pthread_t thread;

	/* No SA_RESTART: the waiting read must surface EINTR to user space. */
	CHECK(sigemptyset(&action.sa_mask) == 0);
	CHECK(sigaction(SIGUSR1, &action, &previous) == 0);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_CLEAR) == 0);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_GET_STATS, &stats) == 0);
	CHECK(pthread_create(&thread, NULL, blocked_reader, NULL) == 0);
	wait_for_block(fd, stats.blocked_reads);
	CHECK(pthread_kill(thread, SIGUSR1) == 0);
	CHECK(pthread_join(thread, NULL) == 0);
	CHECK(reader_result == -1 && reader_errno == EINTR);
	CHECK(sigaction(SIGUSR1, &previous, NULL) == 0);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_GET_STATS, &stats) == 0);
	CHECK(stats.stored_bytes == 0);
}

static void interrupted_write(int fd)
{
	struct sigaction action = { .sa_handler = interrupt_handler };
	struct sigaction previous;
	struct ringbuf_char_stats before, after;
	struct timespec pause = { .tv_nsec = 1000000 };
	pthread_t thread;
	unsigned char *full;
	unsigned int i;

	CHECK(sigemptyset(&action.sa_mask) == 0);
	CHECK(sigaction(SIGUSR1, &action, &previous) == 0);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_CLEAR) == 0);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_GET_STATS, &before) == 0);
	full = malloc((size_t)before.current_capacity);
	CHECK(full != NULL);
	memset(full, 'F', (size_t)before.current_capacity);
	CHECK(write(fd, full, (size_t)before.current_capacity) == (ssize_t)before.current_capacity);
	writer_fd = open(RINGBUF_CHAR_DEVICE_PATH, O_WRONLY);
	CHECK(writer_fd >= 0);
	CHECK(pthread_create(&thread, NULL, blocked_writer, NULL) == 0);
	for (i = 0; i < 3000; i++) {
		CHECK(ioctl(fd, RINGBUF_CHAR_IOC_GET_STATS, &after) == 0);
		if (after.blocked_writes > before.blocked_writes)
			break;
		nanosleep(&pause, NULL);
	}
	CHECK(i < 3000);
	CHECK(pthread_kill(thread, SIGUSR1) == 0);
	CHECK(pthread_join(thread, NULL) == 0);
	CHECK(writer_result == -1 && writer_errno == EINTR);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_GET_STATS, &after) == 0);
	CHECK(after.stored_bytes == before.current_capacity);
	CHECK(close(writer_fd) == 0);
	free(full);
	CHECK(sigaction(SIGUSR1, &previous, NULL) == 0);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_CLEAR) == 0);
}

int main(void)
{
	long page = sysconf(_SC_PAGESIZE);
	int fd = open(RINGBUF_CHAR_DEVICE_PATH, O_RDWR | O_NONBLOCK);
	unsigned char *memory;
	unsigned char result[64];
	struct ringbuf_char_stats stats;
	ssize_t transferred;
	__u32 mode = 0;

	CHECK(fd >= 0 && page > 0);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_SET_MODE, &mode) == 0);
	reader_fd = open(RINGBUF_CHAR_DEVICE_PATH, O_RDONLY);
	CHECK(reader_fd >= 0);
	control_wakeup(fd, RINGBUF_CHAR_IOC_CLEAR, 0);
	control_wakeup(fd, RINGBUF_CHAR_IOC_SET_CAPACITY, 0);
	control_wakeup(fd, RINGBUF_CHAR_IOC_SET_MODE, 0);
	control_wakeup(fd, RINGBUF_CHAR_IOC_SET_MODE, 1);
	interrupted_read(fd);
	interrupted_write(fd);

	memory = mmap(NULL, (size_t)page * 2, PROT_READ | PROT_WRITE,
		      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	CHECK(memory != MAP_FAILED);
	memset(memory, 'P', (size_t)page);
	CHECK(mprotect(memory + page, (size_t)page, PROT_NONE) == 0);
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_CLEAR) == 0);
	transferred = write(fd, memory + page - 32, 64);
	/* Some architectures may fault before copying any bytes. */
	CHECK((transferred > 0 && transferred <= 32) ||
	      (transferred == -1 && errno == EFAULT));
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_GET_STATS, &stats) == 0);
	CHECK(stats.stored_bytes == (__u64)(transferred > 0 ? transferred : 0));
	if (transferred > 0) {
		CHECK(read(fd, result, sizeof(result)) == transferred);
		CHECK(memcmp(result, memory + page - 32, (size_t)transferred) == 0);
	}
	CHECK(write(fd, memory, 64) == 64);
	transferred = read(fd, memory + page - 32, 64);
	CHECK((transferred > 0 && transferred <= 32) ||
	      (transferred == -1 && errno == EFAULT));
	CHECK(ioctl(fd, RINGBUF_CHAR_IOC_GET_STATS, &stats) == 0);
	CHECK(stats.stored_bytes == 64 - (__u64)(transferred > 0 ? transferred : 0));
	CHECK(read(fd, result, sizeof(result)) == (ssize_t)stats.stored_bytes);
	CHECK(munmap(memory, (size_t)page * 2) == 0);
	CHECK(close(reader_fd) == 0);
	CHECK(close(fd) == 0);
	puts("PASS: control wakeups, interrupted read/write, and partial user-memory faults");
	return 0;
}
