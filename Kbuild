ccflags-y += -I$(src)/include

obj-m += ringbuf_char.o
ringbuf_char-y := kernel/ringbuf_char.o kernel/ringbuf_char_buffer.o

ifeq ($(RINGBUF_KUNIT),1)
obj-m += ringbuf_char_test.o
ringbuf_char_test-y := kernel/ringbuf_char_buffer.o kernel/ringbuf_char_buffer_test.o
endif

