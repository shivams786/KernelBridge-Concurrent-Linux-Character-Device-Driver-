/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHIVAM_CHAR_BUFFER_H
#define SHIVAM_CHAR_BUFFER_H

#include <linux/types.h>

struct shivam_char_buffer {
	u8 *data;
	size_t capacity;
	size_t len;
	size_t read_pos;
	size_t write_pos;
};

int shivam_char_buffer_init(struct shivam_char_buffer *buffer, size_t capacity);
void shivam_char_buffer_cleanup(struct shivam_char_buffer *buffer);
size_t shivam_char_buffer_stored(const struct shivam_char_buffer *buffer);
size_t shivam_char_buffer_available(const struct shivam_char_buffer *buffer);
size_t shivam_char_buffer_read(struct shivam_char_buffer *buffer, u8 *dst,
			       size_t count);
size_t shivam_char_buffer_write(struct shivam_char_buffer *buffer,
				const u8 *src, size_t count);
void shivam_char_buffer_clear(struct shivam_char_buffer *buffer);
int shivam_char_buffer_resize(struct shivam_char_buffer *buffer,
			      size_t new_capacity);

size_t shivam_char_buffer_read_span(const struct shivam_char_buffer *buffer,
				    const u8 **ptr);
void shivam_char_buffer_consume(struct shivam_char_buffer *buffer,
				size_t count);
size_t shivam_char_buffer_write_span(const struct shivam_char_buffer *buffer,
				     u8 **ptr);
void shivam_char_buffer_commit(struct shivam_char_buffer *buffer,
			       size_t count);

#endif /* SHIVAM_CHAR_BUFFER_H */

