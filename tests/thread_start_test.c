// SPDX-License-Identifier: GPL-2.0-only
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int concurrent_test_main(int argc, char **argv);
int __wrap_pthread_create(pthread_t *, const pthread_attr_t *,
			 void *(*)(void *), void *);
int __wrap_pthread_join(pthread_t, void **);

static unsigned int fail_at, attempts, started, joined;
static pthread_t handles[4];
static int seen[4];

int __wrap_pthread_create(pthread_t *thread, const pthread_attr_t *attr,
			 void *(*entry)(void *), void *arg)
{
	(void)attr;
	(void)entry;
	(void)arg;
	if (attempts++ == fail_at)
		return EAGAIN;
	/* No workers execute: this isolates startup and cleanup from device I/O. */
	memset(thread, (int)started + 1, sizeof(*thread));
	handles[started++] = *thread;
	return 0;
}

int __wrap_pthread_join(pthread_t thread, void **result)
{
	unsigned int i;
	(void)result;
	for (i = 0; i < started; i++) {
		if (memcmp(&thread, &handles[i], sizeof(thread)) == 0 && !seen[i]) {
			seen[i] = 1;
			joined++;
			return 0;
		}
	}
	fputs("FAIL: joined an unstarted or already joined thread\n", stderr);
	exit(2);
}

int main(void)
{
	char *args[] = { "concurrent_test", "--readers", "2", "--writers",
			 "2", "--messages", "1", NULL };
	for (fail_at = 0; fail_at < 4; fail_at++) {
		attempts = started = joined = 0;
		memset(seen, 0, sizeof(seen));
		if (concurrent_test_main(7, args) != 1 || started != fail_at ||
		    joined != started || attempts != fail_at + 1) {
			fprintf(stderr, "FAIL: startup failure at position %u\n", fail_at);
			return 1;
		}
	}
	puts("PASS: all four thread startup failure positions");
	return 0;
}
