// SPDX-License-Identifier: GPL-2.0-only
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "shivam_char_ioctl.h"

#ifndef O_CLOEXEC
#define O_CLOEXEC 0
#endif

#define FRAME_MAGIC "SCF1"
#define FRAME_HEADER_SIZE 20U
#define DEFAULT_WRITERS 4U
#define DEFAULT_READERS 4U
#define DEFAULT_MESSAGES 1000U
#define DEFAULT_MESSAGE_SIZE 64U
#define MAX_THREADS 64U
#define MAX_MESSAGES 100000U
#define MAX_MESSAGE_SIZE 4096U
#define READ_CHUNK_SIZE 4096U

struct test_options {
	const char *device_path;
	unsigned int writers;
	unsigned int readers;
	unsigned int messages;
	unsigned int message_size;
};

struct run_stats {
	atomic_ullong writes_attempted;
	atomic_ullong writes_completed;
	atomic_ullong reads_completed;
	atomic_ullong bytes_written;
	atomic_ullong bytes_read;
	atomic_ullong frames_validated;
	atomic_ullong validation_failures;
	atomic_ullong writer_threads_done;
};

struct shared_state {
	struct test_options opts;
	struct run_stats stats;
	pthread_mutex_t write_lock;
	pthread_mutex_t read_lock;
	unsigned char *seen;
	size_t seen_count;
	unsigned char *stream;
	size_t stream_len;
	size_t stream_cap;
	atomic_bool stop;
};

struct thread_arg {
	struct shared_state *state;
	unsigned int id;
};

static void usage(FILE *stream, const char *program)
{
	fprintf(stream,
		"Usage: %s [OPTIONS]\n"
		"\n"
		"Options:\n"
		"  --device PATH       Device node (default: %s)\n"
		"  --writers N         Writer threads, 1..64 (default: 4)\n"
		"  --readers N         Reader threads, 1..64 (default: 4)\n"
		"  --messages N        Messages per writer, 1..100000 (default: 1000)\n"
		"  --size N            Framed message size, 20..4096 (default: 64)\n"
		"  --help              Show this help\n",
		program, SHIVAM_CHAR_DEVICE_PATH);
}

static int parse_uint(const char *text, unsigned int min_value,
		      unsigned int max_value, unsigned int *out)
{
	unsigned long value;
	char *end = NULL;

	if (!text || !*text || text[0] == '-')
		return -EINVAL;

	errno = 0;
	value = strtoul(text, &end, 10);
	if (errno == ERANGE || end == text || *end != '\0')
		return -EINVAL;
	if (value < min_value || value > max_value)
		return -ERANGE;

	*out = (unsigned int)value;
	return 0;
}

static void sleep_ms(long milliseconds)
{
	struct timespec req;

	req.tv_sec = milliseconds / 1000L;
	req.tv_nsec = (milliseconds % 1000L) * 1000000L;
	while (nanosleep(&req, &req) == -1 && errno == EINTR) {
	}
}

static void put_be32(unsigned char *dst, uint32_t value)
{
	dst[0] = (unsigned char)((value >> 24) & 0xffU);
	dst[1] = (unsigned char)((value >> 16) & 0xffU);
	dst[2] = (unsigned char)((value >> 8) & 0xffU);
	dst[3] = (unsigned char)(value & 0xffU);
}

static uint32_t get_be32(const unsigned char *src)
{
	return ((uint32_t)src[0] << 24) | ((uint32_t)src[1] << 16) |
	       ((uint32_t)src[2] << 8) | (uint32_t)src[3];
}

static uint32_t frame_checksum(uint32_t writer_id, uint32_t sequence,
			       const unsigned char *payload,
			       uint32_t payload_len)
{
	uint32_t checksum = 2166136261U ^ writer_id ^ sequence ^ payload_len;
	uint32_t index;

	for (index = 0; index < payload_len; index++) {
		checksum ^= payload[index];
		checksum *= 16777619U;
	}

	return checksum;
}

static void build_frame(unsigned char *frame, unsigned int frame_size,
			unsigned int writer_id, unsigned int sequence)
{
	uint32_t payload_len = frame_size - FRAME_HEADER_SIZE;
	unsigned char *payload = frame + FRAME_HEADER_SIZE;
	uint32_t checksum;
	uint32_t index;

	memcpy(frame, FRAME_MAGIC, 4);
	put_be32(frame + 4, writer_id);
	put_be32(frame + 8, sequence);
	put_be32(frame + 12, payload_len);

	for (index = 0; index < payload_len; index++)
		payload[index] = (unsigned char)((writer_id * 31U + sequence +
						  index) & 0xffU);

	checksum = frame_checksum(writer_id, sequence, payload, payload_len);
	put_be32(frame + 16, checksum);
}

static int open_device(const char *path, int flags)
{
	int fd;

	do {
		fd = open(path, flags | O_CLOEXEC | O_NONBLOCK);
	} while (fd == -1 && errno == EINTR);

	return fd;
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

static int write_frame_retry(struct shared_state *state, int fd,
			     const unsigned char *frame, size_t frame_size)
{
	size_t offset = 0;

	while (offset < frame_size && !atomic_load(&state->stop)) {
		ssize_t ret = write_retry(fd, frame + offset, frame_size - offset);

		if (ret == -1) {
			if (errno == EAGAIN || errno == EWOULDBLOCK) {
				sleep_ms(1);
				continue;
			}
			return -errno;
		}
		if (ret == 0)
			return -EIO;

		offset += (size_t)ret;
	}

	return offset == frame_size ? 0 : -ECANCELED;
}

static int ensure_stream_capacity(struct shared_state *state, size_t extra)
{
	unsigned char *new_stream;
	size_t needed = state->stream_len + extra;
	size_t new_cap;

	if (needed <= state->stream_cap)
		return 0;

	new_cap = state->stream_cap == 0 ? READ_CHUNK_SIZE : state->stream_cap;
	while (new_cap < needed) {
		if (new_cap > SIZE_MAX / 2)
			return -ENOMEM;
		new_cap *= 2;
	}

	new_stream = realloc(state->stream, new_cap);
	if (!new_stream)
		return -ENOMEM;

	state->stream = new_stream;
	state->stream_cap = new_cap;
	return 0;
}

static size_t find_magic_offset(const unsigned char *data, size_t len)
{
	size_t index;

	for (index = 1; index + 4 <= len; index++) {
		if (memcmp(data + index, FRAME_MAGIC, 4) == 0)
			return index;
	}

	return len;
}

static void consume_stream(struct shared_state *state, size_t count)
{
	if (count >= state->stream_len) {
		state->stream_len = 0;
		return;
	}

	memmove(state->stream, state->stream + count, state->stream_len - count);
	state->stream_len -= count;
}

static void validate_available_frames(struct shared_state *state)
{
	const struct test_options *opts = &state->opts;

	for (;;) {
		uint32_t writer_id;
		uint32_t sequence;
		uint32_t payload_len;
		uint32_t expected_checksum;
		uint32_t actual_checksum;
		size_t frame_size;
		size_t seen_index;

		if (state->stream_len < FRAME_HEADER_SIZE)
			return;

		if (memcmp(state->stream, FRAME_MAGIC, 4) != 0) {
			size_t offset = find_magic_offset(state->stream,
							 state->stream_len);

			atomic_fetch_add(&state->stats.validation_failures, 1);
			if (offset == state->stream_len) {
				size_t keep = state->stream_len < 3 ?
					      state->stream_len : 3;

				if (keep > 0)
					memmove(state->stream,
						state->stream +
							state->stream_len - keep,
						keep);
				state->stream_len = keep;
				return;
			}
			consume_stream(state, offset);
			continue;
		}

		writer_id = get_be32(state->stream + 4);
		sequence = get_be32(state->stream + 8);
		payload_len = get_be32(state->stream + 12);
		expected_checksum = get_be32(state->stream + 16);
		frame_size = (size_t)payload_len + FRAME_HEADER_SIZE;

		if (payload_len > MAX_MESSAGE_SIZE ||
		    frame_size != opts->message_size) {
			atomic_fetch_add(&state->stats.validation_failures, 1);
			consume_stream(state, 1);
			continue;
		}

		if (state->stream_len < frame_size)
			return;

		actual_checksum = frame_checksum(writer_id, sequence,
						 state->stream +
							 FRAME_HEADER_SIZE,
						 payload_len);
		if (writer_id >= opts->writers || sequence >= opts->messages) {
			atomic_fetch_add(&state->stats.validation_failures, 1);
		} else {
			seen_index = (size_t)writer_id * opts->messages +
				     sequence;
			if (seen_index >= state->seen_count ||
			    state->seen[seen_index] != 0 ||
			    actual_checksum != expected_checksum) {
				atomic_fetch_add(&state->stats.validation_failures,
						 1);
				consume_stream(state, frame_size);
				continue;
			}
			state->seen[seen_index] = 1;
			atomic_fetch_add(&state->stats.frames_validated, 1);
		}

		consume_stream(state, frame_size);
	}
}

static void append_and_validate(struct shared_state *state,
				const unsigned char *data, size_t len)
{
	if (ensure_stream_capacity(state, len) != 0) {
		atomic_fetch_add(&state->stats.validation_failures, 1);
		atomic_store(&state->stop, true);
		return;
	}

	memcpy(state->stream + state->stream_len, data, len);
	state->stream_len += len;
	validate_available_frames(state);
}

static void *writer_thread(void *arg)
{
	struct thread_arg *thread = arg;
	struct shared_state *state = thread->state;
	const struct test_options *opts = &state->opts;
	unsigned char *frame;
	unsigned int sequence;
	int fd;

	frame = malloc(opts->message_size);
	if (!frame) {
		atomic_fetch_add(&state->stats.validation_failures, 1);
		atomic_store(&state->stop, true);
		return NULL;
	}

	fd = open_device(opts->device_path, O_WRONLY);
	if (fd == -1) {
		fprintf(stderr, "writer %u open failed: %s\n", thread->id,
			strerror(errno));
		atomic_fetch_add(&state->stats.validation_failures, 1);
		atomic_store(&state->stop, true);
		free(frame);
		return NULL;
	}

	for (sequence = 0; sequence < opts->messages &&
			   !atomic_load(&state->stop);
	     sequence++) {
		int ret;

		build_frame(frame, opts->message_size, thread->id, sequence);
		atomic_fetch_add(&state->stats.writes_attempted, 1);

		pthread_mutex_lock(&state->write_lock);
		ret = write_frame_retry(state, fd, frame, opts->message_size);
		pthread_mutex_unlock(&state->write_lock);

		if (ret != 0) {
			fprintf(stderr, "writer %u write failed: %s\n",
				thread->id, strerror(-ret));
			atomic_fetch_add(&state->stats.validation_failures, 1);
			atomic_store(&state->stop, true);
			break;
		}

		atomic_fetch_add(&state->stats.writes_completed, 1);
		atomic_fetch_add(&state->stats.bytes_written,
				 opts->message_size);
	}

	close(fd);
	free(frame);
	atomic_fetch_add(&state->stats.writer_threads_done, 1);
	return NULL;
}

static bool all_writers_done(const struct shared_state *state)
{
	return atomic_load(&state->stats.writer_threads_done) >=
	       state->opts.writers;
}

static void *reader_thread(void *arg)
{
	struct thread_arg *thread = arg;
	struct shared_state *state = thread->state;
	const struct test_options *opts = &state->opts;
	unsigned char buffer[READ_CHUNK_SIZE];
	unsigned int idle_after_writers = 0;
	int fd;

	fd = open_device(opts->device_path, O_RDONLY);
	if (fd == -1) {
		fprintf(stderr, "reader %u open failed: %s\n", thread->id,
			strerror(errno));
		atomic_fetch_add(&state->stats.validation_failures, 1);
		atomic_store(&state->stop, true);
		return NULL;
	}

	while (!atomic_load(&state->stop)) {
		ssize_t ret;

		pthread_mutex_lock(&state->read_lock);
		ret = read_retry(fd, buffer, sizeof(buffer));
		if (ret > 0)
			append_and_validate(state, buffer, (size_t)ret);
		pthread_mutex_unlock(&state->read_lock);

		if (ret > 0) {
			atomic_fetch_add(&state->stats.reads_completed, 1);
			atomic_fetch_add(&state->stats.bytes_read, (size_t)ret);
			idle_after_writers = 0;
			if (atomic_load(&state->stats.frames_validated) >=
			    (unsigned long long)opts->writers * opts->messages)
				break;
			continue;
		}

		if (ret == -1 && errno != EAGAIN && errno != EWOULDBLOCK) {
			fprintf(stderr, "reader %u read failed: %s\n",
				thread->id, strerror(errno));
			atomic_fetch_add(&state->stats.validation_failures, 1);
			atomic_store(&state->stop, true);
			break;
		}

		if (all_writers_done(state)) {
			if (atomic_load(&state->stats.frames_validated) >=
			    (unsigned long long)opts->writers * opts->messages)
				break;
			idle_after_writers++;
			if (idle_after_writers > 2000U)
				break;
		}

		sleep_ms(1);
	}

	close(fd);
	return NULL;
}

static double elapsed_seconds(struct timespec start, struct timespec end)
{
	double seconds = (double)(end.tv_sec - start.tv_sec);
	double nanos = (double)(end.tv_nsec - start.tv_nsec) / 1000000000.0;

	return seconds + nanos;
}

static unsigned long long counter_value(atomic_ullong *counter)
{
	return atomic_load(counter);
}

static int parse_args(int argc, char **argv, struct test_options *opts)
{
	int index;

	opts->device_path = SHIVAM_CHAR_DEVICE_PATH;
	opts->writers = DEFAULT_WRITERS;
	opts->readers = DEFAULT_READERS;
	opts->messages = DEFAULT_MESSAGES;
	opts->message_size = DEFAULT_MESSAGE_SIZE;

	for (index = 1; index < argc; index++) {
		if (strcmp(argv[index], "--help") == 0 ||
		    strcmp(argv[index], "-h") == 0) {
			usage(stdout, argv[0]);
			exit(0);
		} else if (strcmp(argv[index], "--device") == 0) {
			if (index + 1 >= argc) {
				fprintf(stderr, "--device requires PATH\n");
				return 1;
			}
			opts->device_path = argv[++index];
		} else if (strcmp(argv[index], "--writers") == 0) {
			if (index + 1 >= argc ||
			    parse_uint(argv[++index], 1, MAX_THREADS,
				       &opts->writers)) {
				fprintf(stderr, "invalid --writers value\n");
				return 1;
			}
		} else if (strcmp(argv[index], "--readers") == 0) {
			if (index + 1 >= argc ||
			    parse_uint(argv[++index], 1, MAX_THREADS,
				       &opts->readers)) {
				fprintf(stderr, "invalid --readers value\n");
				return 1;
			}
		} else if (strcmp(argv[index], "--messages") == 0) {
			if (index + 1 >= argc ||
			    parse_uint(argv[++index], 1, MAX_MESSAGES,
				       &opts->messages)) {
				fprintf(stderr, "invalid --messages value\n");
				return 1;
			}
		} else if (strcmp(argv[index], "--size") == 0) {
			if (index + 1 >= argc ||
			    parse_uint(argv[++index], FRAME_HEADER_SIZE,
				       MAX_MESSAGE_SIZE,
				       &opts->message_size)) {
				fprintf(stderr, "invalid --size value\n");
				return 1;
			}
		} else {
			fprintf(stderr, "unknown option: %s\n", argv[index]);
			return 1;
		}
	}

	return 0;
}

static int init_state(struct shared_state *state, const struct test_options *opts)
{
	size_t expected;

	if (opts->messages != 0 &&
	    opts->writers > SIZE_MAX / opts->messages)
		return -ENOMEM;

	expected = (size_t)opts->writers * opts->messages;
	memset(state, 0, sizeof(*state));
	state->opts = *opts;
	state->seen_count = expected;
	state->seen = calloc(expected, sizeof(*state->seen));
	if (!state->seen)
		return -ENOMEM;

	if (pthread_mutex_init(&state->write_lock, NULL) != 0) {
		free(state->seen);
		return -EINVAL;
	}

	if (pthread_mutex_init(&state->read_lock, NULL) != 0) {
		pthread_mutex_destroy(&state->write_lock);
		free(state->seen);
		return -EINVAL;
	}

	atomic_init(&state->stop, false);
	atomic_init(&state->stats.writes_attempted, 0);
	atomic_init(&state->stats.writes_completed, 0);
	atomic_init(&state->stats.reads_completed, 0);
	atomic_init(&state->stats.bytes_written, 0);
	atomic_init(&state->stats.bytes_read, 0);
	atomic_init(&state->stats.frames_validated, 0);
	atomic_init(&state->stats.validation_failures, 0);
	atomic_init(&state->stats.writer_threads_done, 0);
	return 0;
}

static void destroy_state(struct shared_state *state)
{
	pthread_mutex_destroy(&state->read_lock);
	pthread_mutex_destroy(&state->write_lock);
	free(state->stream);
	free(state->seen);
}

int main(int argc, char **argv)
{
	struct test_options opts;
	struct shared_state state;
	pthread_t *writer_threads = NULL;
	pthread_t *reader_threads = NULL;
	struct thread_arg *writer_args = NULL;
	struct thread_arg *reader_args = NULL;
	struct timespec start;
	struct timespec end;
	unsigned int index;
	unsigned long long expected_frames;
	unsigned long long missing = 0;
	unsigned long long failures;
	double seconds;
	int exit_code = 1;

	if (parse_args(argc, argv, &opts) != 0) {
		usage(stderr, argv[0]);
		return 1;
	}

	if (init_state(&state, &opts) != 0) {
		fprintf(stderr, "failed to initialize test state\n");
		return 1;
	}

	writer_threads = calloc(opts.writers, sizeof(*writer_threads));
	reader_threads = calloc(opts.readers, sizeof(*reader_threads));
	writer_args = calloc(opts.writers, sizeof(*writer_args));
	reader_args = calloc(opts.readers, sizeof(*reader_args));
	if (!writer_threads || !reader_threads || !writer_args || !reader_args) {
		fprintf(stderr, "failed to allocate thread arrays\n");
		goto out;
	}

	clock_gettime(CLOCK_MONOTONIC, &start);

	for (index = 0; index < opts.readers; index++) {
		reader_args[index].state = &state;
		reader_args[index].id = index;
		if (pthread_create(&reader_threads[index], NULL, reader_thread,
				   &reader_args[index]) != 0) {
			fprintf(stderr, "failed to start reader thread %u\n",
				index);
			atomic_store(&state.stop, true);
			goto join_started;
		}
	}

	for (index = 0; index < opts.writers; index++) {
		writer_args[index].state = &state;
		writer_args[index].id = index;
		if (pthread_create(&writer_threads[index], NULL, writer_thread,
				   &writer_args[index]) != 0) {
			fprintf(stderr, "failed to start writer thread %u\n",
				index);
			atomic_store(&state.stop, true);
			goto join_started;
		}
	}

join_started:
	for (index = 0; index < opts.writers; index++) {
		if (writer_args[index].state)
			pthread_join(writer_threads[index], NULL);
	}

	for (index = 0; index < opts.readers; index++) {
		if (reader_args[index].state)
			pthread_join(reader_threads[index], NULL);
	}

	clock_gettime(CLOCK_MONOTONIC, &end);

	expected_frames = (unsigned long long)opts.writers * opts.messages;
	for (index = 0; index < state.seen_count; index++) {
		if (state.seen[index] == 0)
			missing++;
	}
	if (state.stream_len != 0)
		atomic_fetch_add(&state.stats.validation_failures, 1);

	failures = counter_value(&state.stats.validation_failures);
	seconds = elapsed_seconds(start, end);
	if (seconds <= 0.0)
		seconds = 0.000001;

	printf("writers: %u\n", opts.writers);
	printf("readers: %u\n", opts.readers);
	printf("messages_per_writer: %u\n", opts.messages);
	printf("message_size: %u\n", opts.message_size);
	printf("writes_attempted: %llu\n",
	       counter_value(&state.stats.writes_attempted));
	printf("writes_completed: %llu\n",
	       counter_value(&state.stats.writes_completed));
	printf("reads_completed: %llu\n",
	       counter_value(&state.stats.reads_completed));
	printf("bytes_written: %llu\n",
	       counter_value(&state.stats.bytes_written));
	printf("bytes_read: %llu\n", counter_value(&state.stats.bytes_read));
	printf("frames_validated: %llu\n",
	       counter_value(&state.stats.frames_validated));
	printf("missing_messages: %llu\n", missing);
	printf("validation_failures: %llu\n", failures);
	printf("elapsed_seconds: %.6f\n", seconds);
	printf("throughput_mib_s: %.3f\n",
	       ((double)counter_value(&state.stats.bytes_read) /
		(1024.0 * 1024.0)) /
		       seconds);

	if (counter_value(&state.stats.writes_completed) == expected_frames &&
	    counter_value(&state.stats.frames_validated) == expected_frames &&
	    missing == 0 && failures == 0)
		exit_code = 0;

out:
	free(reader_args);
	free(writer_args);
	free(reader_threads);
	free(writer_threads);
	destroy_state(&state);
	return exit_code;
}
