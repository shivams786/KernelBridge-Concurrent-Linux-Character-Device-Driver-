CC ?= gcc
.DEFAULT_GOAL := all
CPPFLAGS ?= -I../include
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -pedantic -O2 -g -D_POSIX_C_SOURCE=200809L

.PHONY: all clean asan test

test: thread_start_test
	./thread_start_test

concurrent_test_main.o: concurrent_test.c ../include/ringbuf_char_ioctl.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -Dmain=concurrent_test_main -pthread -c -o $@ $<

thread_start_test: ../tests/thread_start_test.c concurrent_test_main.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -pthread -o $@ $^ -Wl,--wrap=pthread_create -Wl,--wrap=pthread_join

all: ringbuf_char_client concurrent_test regression_test abi_dump

abi_dump: abi_dump.c ../include/ringbuf_char_ioctl.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ abi_dump.c

regression_test: regression_test.c ../include/ringbuf_char_ioctl.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -pthread -o $@ regression_test.c

ringbuf_char_client: client.c ../include/ringbuf_char_ioctl.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ client.c

concurrent_test: concurrent_test.c ../include/ringbuf_char_ioctl.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -pthread -o $@ concurrent_test.c

asan: CFLAGS += -fsanitize=address -fno-omit-frame-pointer
asan: clean all

clean:
	rm -f ringbuf_char_client concurrent_test regression_test abi_dump thread_start_test concurrent_test_main.o

