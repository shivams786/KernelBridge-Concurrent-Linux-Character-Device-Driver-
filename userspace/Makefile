CC ?= gcc
CPPFLAGS ?= -I../include
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -pedantic -O2 -g -D_POSIX_C_SOURCE=200809L

.PHONY: all clean asan

all: ringbuf_char_client concurrent_test

ringbuf_char_client: client.c ../include/ringbuf_char_ioctl.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ client.c

concurrent_test: concurrent_test.c ../include/ringbuf_char_ioctl.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -pthread -o $@ concurrent_test.c

asan: CFLAGS += -fsanitize=address -fno-omit-frame-pointer
asan: clean all

clean:
	rm -f ringbuf_char_client concurrent_test

