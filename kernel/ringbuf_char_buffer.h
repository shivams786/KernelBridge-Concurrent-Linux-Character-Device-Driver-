/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef RINGBUF_CHAR_BUFFER_H
#define RINGBUF_CHAR_BUFFER_H

#include <linux/types.h>

struct ringbuf_char_buffer {
	u8 *data;
	size_t capacity;
	size_t len;
	size_t read_pos;
	size_t write_pos;
};

int ringbuf_char_buffer_init(struct ringbuf_char_buffer *buffer, size_t capacity);
void ringbuf_char_buffer_cleanup(struct ringbuf_char_buffer *buffer);
size_t ringbuf_char_buffer_stored(const struct ringbuf_char_buffer *buffer);
size_t ringbuf_char_buffer_available(const struct ringbuf_char_buffer *buffer);
size_t ringbuf_char_buffer_read(struct ringbuf_char_buffer *buffer, u8 *dst,
			       size_t count);
size_t ringbuf_char_buffer_write(struct ringbuf_char_buffer *buffer,
				const u8 *src, size_t count);
void ringbuf_char_buffer_clear(struct ringbuf_char_buffer *buffer);
int ringbuf_char_buffer_resize(struct ringbuf_char_buffer *buffer,
			      size_t new_capacity);

size_t ringbuf_char_buffer_read_span(const struct ringbuf_char_buffer *buffer,
				    const u8 **ptr);
void ringbuf_char_buffer_consume(struct ringbuf_char_buffer *buffer,
				size_t count);
size_t ringbuf_char_buffer_write_span(const struct ringbuf_char_buffer *buffer,
				     u8 **ptr);
void ringbuf_char_buffer_commit(struct ringbuf_char_buffer *buffer,
			       size_t count);

#endif /* RINGBUF_CHAR_BUFFER_H */

