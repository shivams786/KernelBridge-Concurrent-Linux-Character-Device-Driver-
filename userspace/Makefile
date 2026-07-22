CC ?= gcc
CPPFLAGS ?= -I../include
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -pedantic -O2 -g -D_POSIX_C_SOURCE=200809L

.PHONY: all clean asan

all: shivam_char_client concurrent_test

shivam_char_client: client.c ../include/shivam_char_ioctl.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ client.c

concurrent_test: concurrent_test.c ../include/shivam_char_ioctl.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -pthread -o $@ concurrent_test.c

asan: CFLAGS += -fsanitize=address -fno-omit-frame-pointer
asan: clean all

clean:
	rm -f shivam_char_client concurrent_test

