// SPDX-License-Identifier: GPL-2.0-only
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/string.h>
#include <linux/vmalloc.h>

#include <ringbuf_char_ioctl.h>

#include "ringbuf_char_buffer.h"

static bool ringbuf_char_capacity_valid(size_t capacity)
{
	return capacity >= RINGBUF_CHAR_MIN_CAPACITY &&
	       capacity <= RINGBUF_CHAR_MAX_CAPACITY;
}

int ringbuf_char_buffer_init(struct ringbuf_char_buffer *buffer, size_t capacity)
{
	if (!buffer || !ringbuf_char_capacity_valid(capacity))
		return -EINVAL;

	buffer->data = kvmalloc(capacity, GFP_KERNEL);
	if (!buffer->data)
		return -ENOMEM;

	buffer->capacity = capacity;
	buffer->len = 0;
	buffer->read_pos = 0;
	buffer->write_pos = 0;

	return 0;
}

void ringbuf_char_buffer_cleanup(struct ringbuf_char_buffer *buffer)
{
	if (!buffer)
		return;

	kvfree(buffer->data);
	buffer->data = NULL;
	buffer->capacity = 0;
	buffer->len = 0;
	buffer->read_pos = 0;
	buffer->write_pos = 0;
}

size_t ringbuf_char_buffer_stored(const struct ringbuf_char_buffer *buffer)
{
	return buffer ? buffer->len : 0;
}

size_t ringbuf_char_buffer_available(const struct ringbuf_char_buffer *buffer)
{
	if (!buffer || buffer->len > buffer->capacity)
		return 0;

	return buffer->capacity - buffer->len;
}

size_t ringbuf_char_buffer_read_span(const struct ringbuf_char_buffer *buffer,
				    const u8 **ptr)
{
	size_t contiguous;

	if (!buffer || !ptr || !buffer->data || buffer->len == 0) {
		if (ptr)
			*ptr = NULL;
		return 0;
	}

	contiguous = min(buffer->len, buffer->capacity - buffer->read_pos);
	*ptr = buffer->data + buffer->read_pos;
	return contiguous;
}

void ringbuf_char_buffer_consume(struct ringbuf_char_buffer *buffer, size_t count)
{
	if (!buffer || !buffer->data || count == 0)
		return;

	count = min(count, buffer->len);
	buffer->read_pos = (buffer->read_pos + count) % buffer->capacity;
	buffer->len -= count;

	if (buffer->len == 0) {
		buffer->read_pos = 0;
		buffer->write_pos = 0;
	}
}

size_t ringbuf_char_buffer_write_span(const struct ringbuf_char_buffer *buffer,
				     u8 **ptr)
{
	size_t available;
	size_t contiguous;

	if (!buffer || !ptr || !buffer->data) {
		if (ptr)
			*ptr = NULL;
		return 0;
	}

	available = ringbuf_char_buffer_available(buffer);
	if (available == 0) {
		*ptr = NULL;
		return 0;
	}

	contiguous = min(available, buffer->capacity - buffer->write_pos);
	*ptr = buffer->data + buffer->write_pos;
	return contiguous;
}

void ringbuf_char_buffer_commit(struct ringbuf_char_buffer *buffer, size_t count)
{
	size_t available;

	if (!buffer || !buffer->data || count == 0)
		return;

	available = ringbuf_char_buffer_available(buffer);
	count = min(count, available);
	buffer->write_pos = (buffer->write_pos + count) % buffer->capacity;
	buffer->len += count;
}

size_t ringbuf_char_buffer_read(struct ringbuf_char_buffer *buffer, u8 *dst,
			       size_t count)
{
	size_t copied = 0;

	if (!buffer || !dst || count == 0)
		return 0;

	while (copied < count && buffer->len > 0) {
		const u8 *src;
		size_t span = ringbuf_char_buffer_read_span(buffer, &src);
		size_t chunk = min(count - copied, span);

		memcpy(dst + copied, src, chunk);
		ringbuf_char_buffer_consume(buffer, chunk);
		copied += chunk;
	}

	return copied;
}

size_t ringbuf_char_buffer_write(struct ringbuf_char_buffer *buffer,
				const u8 *src, size_t count)
{
	size_t copied = 0;

	if (!buffer || !src || count == 0)
		return 0;

	while (copied < count && ringbuf_char_buffer_available(buffer) > 0) {
		u8 *dst;
		size_t span = ringbuf_char_buffer_write_span(buffer, &dst);
		size_t chunk = min(count - copied, span);

		memcpy(dst, src + copied, chunk);
		ringbuf_char_buffer_commit(buffer, chunk);
		copied += chunk;
	}

	return copied;
}

void ringbuf_char_buffer_clear(struct ringbuf_char_buffer *buffer)
{
	if (!buffer)
		return;

	buffer->len = 0;
	buffer->read_pos = 0;
	buffer->write_pos = 0;
}

int ringbuf_char_buffer_resize(struct ringbuf_char_buffer *buffer,
			      size_t new_capacity)
{
	u8 *new_data;
	size_t index;

	if (!buffer || !ringbuf_char_capacity_valid(new_capacity))
		return -EINVAL;

	if (new_capacity < buffer->len)
		return -EMSGSIZE;

	new_data = kvmalloc(new_capacity, GFP_KERNEL);
	if (!new_data)
		return -ENOMEM;

	for (index = 0; index < buffer->len; index++)
		new_data[index] = buffer->data[(buffer->read_pos + index) %
					       buffer->capacity];

	kvfree(buffer->data);
	buffer->data = new_data;
	buffer->capacity = new_capacity;
	buffer->read_pos = 0;
	buffer->write_pos = buffer->len == new_capacity ? 0 : buffer->len;

	return 0;
}
