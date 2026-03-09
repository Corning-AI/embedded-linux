# Kernel module out-of-tree Makefile
#
# Two invocation modes:
#   1. From command line: `make` — sets KERNELDIR then re-invokes via kbuild
#   2. From kbuild system: processes obj-m to build the .ko
#
# KERNELDIR must point to the kernel build tree (with Module.symvers, .config).
# For cross-compilation (building on x86 for ARM64 i.MX8MP):
#   make ARCH=arm64 CROSS_COMPILE=aarch64-poky-linux- \
#        KERNELDIR=/path/to/yocto/tmp/work/.../linux-imx/build

obj-m := hello.o

# Default: use running kernel's build dir (for native build on the EVK itself)
KERNELDIR ?= /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

all:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) clean

.PHONY: all clean
