// SPDX-License-Identifier: GPL-2.0-only
#include <kunit/test.h>
#include <linux/module.h>
#include <linux/string.h>
#include "ringbuf_char_buffer.h"

static int buffer_test_init(struct kunit *test)
{
	struct ringbuf_char_buffer *buffer;

	buffer = kunit_kzalloc(test, sizeof(*buffer), GFP_KERNEL);
	if (!buffer)
		return -ENOMEM;
	test->priv = buffer;
	return ringbuf_char_buffer_init(buffer, 256);
}

static void buffer_test_exit(struct kunit *test)
{
	ringbuf_char_buffer_cleanup(test->priv);
}

static void empty_full_wrap(struct kunit *test)
{
	struct ringbuf_char_buffer *b = test->priv;
	u8 first[200], second[206], output[256];

	memset(first, 'A', sizeof(first));
	memset(second, 'B', sizeof(second));
	KUNIT_EXPECT_EQ(test, ringbuf_char_buffer_read(b, output, 1), (size_t)0);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_write(b, first, 200), (size_t)200);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_read(b, output, 150), (size_t)150);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_write(b, second, 206), (size_t)206);
	KUNIT_EXPECT_EQ(test, ringbuf_char_buffer_available(b), (size_t)0);
	KUNIT_EXPECT_EQ(test, ringbuf_char_buffer_write(b, first, 1), (size_t)0);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_read(b, output, 256), (size_t)256);
	KUNIT_EXPECT_EQ(test, memcmp(output, first, 50), 0);
	KUNIT_EXPECT_EQ(test, memcmp(output + 50, second, 206), 0);
	KUNIT_EXPECT_EQ(test, b->len, (size_t)0);
	KUNIT_EXPECT_EQ(test, b->read_pos, (size_t)0);
	KUNIT_EXPECT_EQ(test, b->write_pos, (size_t)0);
}

static void resize_preserves_wrapped_fifo(struct kunit *test)
{
	struct ringbuf_char_buffer *b = test->priv;
	u8 input[256], output[256];
	size_t i;

	for (i = 0; i < sizeof(input); i++)
		input[i] = (u8)i;
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_write(b, input, 256), (size_t)256);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_read(b, output, 128), (size_t)128);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_write(b, input, 128), (size_t)128);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_resize(b, 512), 0);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_resize(b, 256), 0);
	KUNIT_EXPECT_EQ(test, b->write_pos, (size_t)0);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_read(b, output, 256), (size_t)256);
	KUNIT_EXPECT_EQ(test, memcmp(output, input + 128, 128), 0);
	KUNIT_EXPECT_EQ(test, memcmp(output + 128, input, 128), 0);
}

static void rejected_resize_preserves_state(struct kunit *test)
{
	struct ringbuf_char_buffer *b = test->priv;
	u8 input[300], output[300];
	u8 *allocation;

	memset(input, 0x5a, sizeof(input));
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_resize(b, 512), 0);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_write(b, input, 300), (size_t)300);
	allocation = b->data;
	KUNIT_EXPECT_EQ(test, ringbuf_char_buffer_resize(b, 256), -EMSGSIZE);
	KUNIT_EXPECT_EQ(test, ringbuf_char_buffer_resize(b, 0), -EINVAL);
	KUNIT_EXPECT_EQ(test, ringbuf_char_buffer_resize(b, 65537), -EINVAL);
	KUNIT_EXPECT_PTR_EQ(test, b->data, allocation);
	KUNIT_EXPECT_EQ(test, b->capacity, (size_t)512);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_read(b, output, 300), (size_t)300);
	KUNIT_EXPECT_EQ(test, memcmp(input, output, 300), 0);
	KUNIT_ASSERT_EQ(test, ringbuf_char_buffer_write(b, input, 1), (size_t)1);
	ringbuf_char_buffer_clear(b);
	KUNIT_EXPECT_EQ(test, b->len, (size_t)0);
	KUNIT_EXPECT_EQ(test, ringbuf_char_buffer_available(b), (size_t)512);
}

static struct kunit_case buffer_cases[] = {
	KUNIT_CASE(empty_full_wrap),
	KUNIT_CASE(resize_preserves_wrapped_fifo),
	KUNIT_CASE(rejected_resize_preserves_state),
	{}
};

static struct kunit_suite buffer_suite = {
	.name = "ringbuf-char-buffer",
	.init = buffer_test_init,
	.exit = buffer_test_exit,
	.test_cases = buffer_cases,
};
kunit_test_suite(buffer_suite);
MODULE_LICENSE("GPL");
