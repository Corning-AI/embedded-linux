// SPDX-License-Identifier: GPL-2.0
/*
 * hello.c — Minimal Linux kernel module
 *
 * This is the "Hello World" of kernel programming. It demonstrates:
 *   1. Module entry/exit points (init/exit)
 *   2. Kernel logging with printk() and pr_info() macros
 *   3. Module metadata (license, author, description)
 *   4. The MODULE_* macros that embed info into the .ko binary
 *
 * Build:
 *   make            (requires kernel headers)
 *
 * Usage on the EVK:
 *   scp hello.ko root@<EVK_IP>:/tmp/
 *   insmod /tmp/hello.ko          # loads module, triggers init
 *   dmesg | tail -5               # see "Hello from kernel"
 *   lsmod | grep hello            # verify it's loaded
 *   rmmod hello                   # unloads, triggers exit
 *   dmesg | tail -5               # see "Goodbye from kernel"
 *
 * Key concepts:
 *   - Kernel modules run in ring 0 (kernel space), NOT user space
 *   - A bug here (NULL deref, buffer overflow) crashes the ENTIRE system
 *   - printk() is the kernel equivalent of printf(), outputs to dmesg
 *   - pr_info() is a convenience macro = printk(KERN_INFO ...)
 *   - __init and __exit are section markers: __init code is freed after
 *     boot/load, __exit code is omitted if built-in (not a module)
 */

#include <linux/init.h>    /* __init, __exit macros */
#include <linux/module.h>  /* MODULE_*, module_init/exit */
#include <linux/kernel.h>  /* pr_info, pr_err, etc. */

/*
 * module_init — called when `insmod hello.ko` is run.
 *
 * Return 0 on success, negative errno on failure.
 * If this returns non-zero, the module is NOT loaded.
 */
static int __init hello_init(void)
{
	pr_info("hello: module loaded (i.MX8MP EVK)\n");
	pr_info("hello: running on CPU: %d\n", smp_processor_id());
	return 0;
}

/*
 * module_exit — called when `rmmod hello` is run.
 *
 * No return value. Clean up all resources here.
 * If you skip cleanup (e.g., unregister a device), the kernel
 * will have dangling references → instability.
 */
static void __exit hello_exit(void)
{
	pr_info("hello: module unloaded\n");
}

module_init(hello_init);
module_exit(hello_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("NTU M266 Embedded Linux");
MODULE_DESCRIPTION("Minimal hello-world kernel module for i.MX8MP");
MODULE_VERSION("1.0");
