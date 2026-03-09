# Cross-compile for i.MX8MP (ARM64):
#   make CC=aarch64-poky-linux-gcc
#
# Native build on the EVK (if gcc is installed):
#   make

CC ?= gcc
CFLAGS := -Wall -Wextra -O2

TARGET := capture

.PHONY: all clean

all: $(TARGET)

$(TARGET): capture.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)
