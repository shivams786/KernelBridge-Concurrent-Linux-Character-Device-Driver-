// SPDX-License-Identifier: GPL-2.0-only
#include <stdio.h>
#include <stddef.h>
#include "ringbuf_char_ioctl.h"

/* Freeze the v1 wire layout; these are compilation checks, not compat tests. */
_Static_assert(sizeof(struct ringbuf_char_stats) == 136, "v1 stats size changed");
_Static_assert(offsetof(struct ringbuf_char_stats, current_capacity) == 8, "v1 capacity offset");
_Static_assert(offsetof(struct ringbuf_char_stats, mode) == 128, "v1 mode offset");
_Static_assert(offsetof(struct ringbuf_char_stats, reserved) == 132, "v1 reserved offset");
_Static_assert(_IOC_SIZE(RINGBUF_CHAR_IOC_GET_STATS) == 136, "stats ioctl size");
_Static_assert(_IOC_SIZE(RINGBUF_CHAR_IOC_SET_CAPACITY) == 8, "capacity ioctl size");
_Static_assert(_IOC_SIZE(RINGBUF_CHAR_IOC_SET_MODE) == 4, "mode ioctl size");
_Static_assert(_IOC_DIR(RINGBUF_CHAR_IOC_GET_STATS) == _IOC_READ, "stats direction");
_Static_assert(_IOC_DIR(RINGBUF_CHAR_IOC_SET_CAPACITY) == _IOC_WRITE, "capacity direction");

int main(void)
{
	printf("{\"abi_version\":%u,\"clear\":%lu,\"set_capacity\":%lu,"
	       "\"get_capacity\":%lu,\"min_capacity\":%llu,"
	       "\"max_capacity\":%llu}\n",
	       RINGBUF_CHAR_ABI_VERSION,
	       (unsigned long)RINGBUF_CHAR_IOC_CLEAR,
	       (unsigned long)RINGBUF_CHAR_IOC_SET_CAPACITY,
	       (unsigned long)RINGBUF_CHAR_IOC_GET_CAPACITY,
	       (unsigned long long)RINGBUF_CHAR_MIN_CAPACITY,
	       (unsigned long long)RINGBUF_CHAR_MAX_CAPACITY);
	return 0;
}
