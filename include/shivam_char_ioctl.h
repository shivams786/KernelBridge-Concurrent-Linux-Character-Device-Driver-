/* SPDX-License-Identifier: GPL-2.0-only WITH Linux-syscall-note */
#ifndef SHIVAM_CHAR_IOCTL_H
#define SHIVAM_CHAR_IOCTL_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define SHIVAM_CHAR_DEVICE_NAME "shivam_char"
#define SHIVAM_CHAR_DEVICE_PATH "/dev/shivam_char"
#define SHIVAM_CHAR_CLASS_NAME "shivam_char_class"

#define SHIVAM_CHAR_ABI_VERSION 1U

#define SHIVAM_CHAR_DEFAULT_CAPACITY 4096ULL
#define SHIVAM_CHAR_MIN_CAPACITY 256ULL
#define SHIVAM_CHAR_MAX_CAPACITY 65536ULL

#define SHIVAM_CHAR_MODE_F_NONBLOCK 0x00000001U
#define SHIVAM_CHAR_MODE_VALID_MASK SHIVAM_CHAR_MODE_F_NONBLOCK

struct shivam_char_stats {
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

#define SHIVAM_CHAR_IOC_MAGIC 'S'

#define SHIVAM_CHAR_IOC_CLEAR _IO(SHIVAM_CHAR_IOC_MAGIC, 0x00)
#define SHIVAM_CHAR_IOC_GET_STATS \
	_IOR(SHIVAM_CHAR_IOC_MAGIC, 0x01, struct shivam_char_stats)
#define SHIVAM_CHAR_IOC_SET_CAPACITY \
	_IOW(SHIVAM_CHAR_IOC_MAGIC, 0x02, __u64)
#define SHIVAM_CHAR_IOC_GET_CAPACITY \
	_IOR(SHIVAM_CHAR_IOC_MAGIC, 0x03, __u64)
#define SHIVAM_CHAR_IOC_SET_MODE \
	_IOW(SHIVAM_CHAR_IOC_MAGIC, 0x04, __u32)
#define SHIVAM_CHAR_IOC_RESET_STATS _IO(SHIVAM_CHAR_IOC_MAGIC, 0x05)

#define SHIVAM_CHAR_IOC_MAXNR 0x05

#endif /* SHIVAM_CHAR_IOCTL_H */

