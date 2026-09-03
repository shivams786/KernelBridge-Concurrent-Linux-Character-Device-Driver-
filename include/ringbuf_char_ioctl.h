/* SPDX-License-Identifier: GPL-2.0-only WITH Linux-syscall-note */
#ifndef RINGBUF_CHAR_IOCTL_H
#define RINGBUF_CHAR_IOCTL_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define RINGBUF_CHAR_DEVICE_NAME "ringbuf_char"
#define RINGBUF_CHAR_DEVICE_PATH "/dev/ringbuf_char"
#define RINGBUF_CHAR_CLASS_NAME "ringbuf_char_class"

#define RINGBUF_CHAR_ABI_VERSION 1U

#define RINGBUF_CHAR_DEFAULT_CAPACITY 4096ULL
#define RINGBUF_CHAR_MIN_CAPACITY 256ULL
#define RINGBUF_CHAR_MAX_CAPACITY 65536ULL

#define RINGBUF_CHAR_MODE_F_NONBLOCK 0x00000001U
#define RINGBUF_CHAR_MODE_VALID_MASK RINGBUF_CHAR_MODE_F_NONBLOCK

struct ringbuf_char_stats {
	__u32 abi_version;
	__u32 struct_size;
	__u64 current_capacity;
	__u64 stored_bytes;
	__u64 available_bytes;
	__u64 total_bytes_read;
	__u64 total_bytes_written;
	__u64 read_calls;
	__u64 write_calls;
	__u64 open_calls;
	__u64 current_open_handles;
	__u64 ioctl_calls;
	__u64 failed_operations;
	__u64 blocked_reads;
	__u64 blocked_writes;
	__u64 clears;
	__u64 resizes;
	__u32 mode;
	__u32 reserved;
};

#define RINGBUF_CHAR_IOC_MAGIC 'R'

#define RINGBUF_CHAR_IOC_CLEAR _IO(RINGBUF_CHAR_IOC_MAGIC, 0x00)
#define RINGBUF_CHAR_IOC_GET_STATS \
	_IOR(RINGBUF_CHAR_IOC_MAGIC, 0x01, struct ringbuf_char_stats)
#define RINGBUF_CHAR_IOC_SET_CAPACITY \
	_IOW(RINGBUF_CHAR_IOC_MAGIC, 0x02, __u64)
#define RINGBUF_CHAR_IOC_GET_CAPACITY \
	_IOR(RINGBUF_CHAR_IOC_MAGIC, 0x03, __u64)
#define RINGBUF_CHAR_IOC_SET_MODE \
	_IOW(RINGBUF_CHAR_IOC_MAGIC, 0x04, __u32)
#define RINGBUF_CHAR_IOC_RESET_STATS _IO(RINGBUF_CHAR_IOC_MAGIC, 0x05)

#define RINGBUF_CHAR_IOC_MAXNR 0x05

#endif /* RINGBUF_CHAR_IOCTL_H */
