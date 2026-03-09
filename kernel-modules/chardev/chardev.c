// SPDX-License-Identifier: GPL-2.0
/*
 * chardev.c — Linux character device driver
 *
 * Creates /dev/imx8mp_demo that supports:
 *   - open / release (lifecycle management)
 *   - read  (kernel → userspace data transfer via copy_to_user)
 *   - write (userspace → kernel data transfer via copy_from_user)
 *   - ioctl (custom commands: get buffer size, clear buffer)
 *
 * This demonstrates the CORE pattern of Linux device drivers:
 *   1. Register a character device with a major/minor number
 *   2. Implement file_operations (the VFS interface)
 *   3. Handle user ↔ kernel memory boundary safely
 *   4. Use proper synchronization (mutex)
 *   5. Automatic /dev node creation via class + device
 *
 * Build & test:
 *   make
 *   insmod chardev.ko
 *   echo "hello EVK" > /dev/imx8mp_demo
 *   cat /dev/imx8mp_demo
 *   rmmod chardev
 *
 * Architecture (data flow):
 *
 *   User process                    Kernel
 *   ───────────                    ──────
 *   write(fd, "hi", 2)  ───→  chardev_write()
 *                                   │ copy_from_user()
 *                                   ▼
 *                              [kernel buffer]
 *                                   │ copy_to_user()
 *   read(fd, buf, len)  ←───  chardev_read()
 */

#include <linux/init.h>
#include <linux/module.h>
#include <linux/fs.h>        /* file_operations, register_chrdev_region */
#include <linux/cdev.h>      /* cdev_init, cdev_add */
#include <linux/device.h>    /* class_create, device_create → auto /dev node */
#include <linux/uaccess.h>   /* copy_to_user, copy_from_user */
#include <linux/mutex.h>     /* mutex_lock/unlock — protects shared buffer */

#define DEVICE_NAME "imx8mp_demo"
#define CLASS_NAME  "imx8mp"
#define BUF_SIZE    4096

/* ioctl command definitions (see Documentation/userspace-api/ioctl/ioctl-number.rst) */
#define CHARDEV_IOC_MAGIC   'M'                        /* unique magic number */
#define CHARDEV_IOC_GETSIZE _IOR(CHARDEV_IOC_MAGIC, 1, int)   /* read buf size */
#define CHARDEV_IOC_CLEAR   _IO(CHARDEV_IOC_MAGIC, 2)         /* clear buffer */

/* Per-device state — in a real driver, this would be allocated per-instance */
static dev_t          dev_num;      /* major:minor number pair */
static struct cdev    cdev;         /* character device structure */
static struct class  *dev_class;    /* sysfs class → /sys/class/imx8mp/ */

static char           kbuf[BUF_SIZE]; /* kernel-side data buffer */
static size_t         data_len;       /* bytes currently in buffer */
static DEFINE_MUTEX(buf_mutex);       /* protects kbuf and data_len */

/*
 * open — called when userspace does open("/dev/imx8mp_demo", ...).
 *
 * In a real driver, you'd allocate per-file resources here.
 * The inode identifies the device, the file struct tracks this open instance.
 */
static int chardev_open(struct inode *inode, struct file *filp)
{
	pr_info("chardev: opened by PID %d\n", current->pid);
	return 0;
}

/*
 * release — called when the last fd to this file is closed.
 *
 * Counterpart to open(). Free per-file resources here.
 * NOTE: "close" in userspace maps to "release" in the kernel.
 */
static int chardev_release(struct inode *inode, struct file *filp)
{
	pr_info("chardev: closed by PID %d\n", current->pid);
	return 0;
}

/*
 * read — transfers data from kernel buffer to userspace.
 *
 * CRITICAL: Never use memcpy() to write to user pointers!
 * User addresses may be paged out, invalid, or malicious.
 * copy_to_user() handles all of this safely.
 *
 * Returns: number of bytes read, or 0 for EOF, or negative errno.
 */
static ssize_t chardev_read(struct file *filp, char __user *ubuf,
			    size_t count, loff_t *ppos)
{
	size_t bytes_to_read;

	mutex_lock(&buf_mutex);

	if (*ppos >= data_len) {
		mutex_unlock(&buf_mutex);
		return 0; /* EOF: no more data */
	}

	bytes_to_read = min(count, data_len - (size_t)*ppos);

	/*
	 * copy_to_user(dest, src, count)
	 *   dest = user buffer (may fault → sleeps → must not hold spinlock)
	 *   src  = kernel buffer
	 *   returns: number of bytes NOT copied (0 = success)
	 */
	if (copy_to_user(ubuf, kbuf + *ppos, bytes_to_read)) {
		mutex_unlock(&buf_mutex);
		return -EFAULT;  /* bad user address */
	}

	*ppos += bytes_to_read;
	mutex_unlock(&buf_mutex);

	pr_info("chardev: read %zu bytes\n", bytes_to_read);
	return bytes_to_read;
}

/*
 * write — transfers data from userspace into kernel buffer.
 *
 * Same rules apply: always use copy_from_user(), never raw memcpy().
 */
static ssize_t chardev_write(struct file *filp, const char __user *ubuf,
			     size_t count, loff_t *ppos)
{
	size_t bytes_to_write;

	mutex_lock(&buf_mutex);

	bytes_to_write = min(count, (size_t)(BUF_SIZE - 1));

	if (copy_from_user(kbuf, ubuf, bytes_to_write)) {
		mutex_unlock(&buf_mutex);
		return -EFAULT;
	}

	data_len = bytes_to_write;
	kbuf[data_len] = '\0';
	*ppos = 0;

	mutex_unlock(&buf_mutex);

	pr_info("chardev: wrote %zu bytes\n", bytes_to_write);
	return bytes_to_write;
}

/*
 * ioctl — custom device-specific commands.
 *
 * This is how drivers expose non-read/write functionality:
 * hardware configuration, status queries, mode changes, etc.
 * V4L2 cameras use ioctl extensively (VIDIOC_S_FMT, VIDIOC_STREAMON...).
 */
static long chardev_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
	int size;

	switch (cmd) {
	case CHARDEV_IOC_GETSIZE:
		size = BUF_SIZE;
		if (copy_to_user((int __user *)arg, &size, sizeof(size)))
			return -EFAULT;
		return 0;

	case CHARDEV_IOC_CLEAR:
		mutex_lock(&buf_mutex);
		memset(kbuf, 0, BUF_SIZE);
		data_len = 0;
		mutex_unlock(&buf_mutex);
		pr_info("chardev: buffer cleared via ioctl\n");
		return 0;

	default:
		return -ENOTTY;  /* "inappropriate ioctl for device" */
	}
}

/*
 * file_operations — the Virtual File System (VFS) dispatch table.
 *
 * THIS is the heart of a Linux driver. When userspace calls read(),
 * the VFS looks up this table and calls .read = chardev_read.
 * Every /dev node is backed by a file_operations struct.
 *
 * Common ops for different device types:
 *   Block devices: .read_iter, .write_iter (via block layer)
 *   Network:       NOT in /dev — uses socket API instead
 *   Char devices:  .read, .write, .ioctl, .mmap, .poll, .fasync
 */
static const struct file_operations chardev_fops = {
	.owner          = THIS_MODULE,
	.open           = chardev_open,
	.release        = chardev_release,
	.read           = chardev_read,
	.write          = chardev_write,
	.unlocked_ioctl = chardev_ioctl,
};

static int __init chardev_init(void)
{
	int ret;

	/*
	 * Step 1: Allocate a major:minor number dynamically.
	 * Static allocation (register_chrdev_region) risks collisions.
	 * Dynamic allocation lets the kernel pick an unused major number.
	 */
	ret = alloc_chrdev_region(&dev_num, 0, 1, DEVICE_NAME);
	if (ret < 0) {
		pr_err("chardev: failed to alloc chrdev region: %d\n", ret);
		return ret;
	}
	pr_info("chardev: registered major=%d minor=%d\n",
		MAJOR(dev_num), MINOR(dev_num));

	/*
	 * Step 2: Initialize and add the cdev structure.
	 * This links our file_operations to the major:minor number.
	 */
	cdev_init(&cdev, &chardev_fops);
	cdev.owner = THIS_MODULE;
	ret = cdev_add(&cdev, dev_num, 1);
	if (ret < 0) {
		pr_err("chardev: cdev_add failed: %d\n", ret);
		goto err_cdev;
	}

	/*
	 * Step 3: Create a device class in sysfs.
	 * This creates /sys/class/imx8mp/ — visible in sysfs.
	 * udev/mdev watches sysfs and auto-creates /dev nodes.
	 */
	dev_class = class_create(CLASS_NAME);
	if (IS_ERR(dev_class)) {
		ret = PTR_ERR(dev_class);
		pr_err("chardev: class_create failed: %d\n", ret);
		goto err_class;
	}

	/*
	 * Step 4: Create the device node.
	 * This triggers udev to create /dev/imx8mp_demo automatically.
	 * Without this, you'd need `mknod /dev/imx8mp_demo c <major> 0`.
	 */
	if (IS_ERR(device_create(dev_class, NULL, dev_num, NULL, DEVICE_NAME))) {
		ret = -ENOMEM;
		pr_err("chardev: device_create failed\n");
		goto err_device;
	}

	pr_info("chardev: /dev/%s created successfully\n", DEVICE_NAME);
	return 0;

/* Error handling: unwind in reverse order (LIFO) — a universal kernel pattern */
err_device:
	class_destroy(dev_class);
err_class:
	cdev_del(&cdev);
err_cdev:
	unregister_chrdev_region(dev_num, 1);
	return ret;
}

static void __exit chardev_exit(void)
{
	/* Cleanup in reverse order of init — always! */
	device_destroy(dev_class, dev_num);
	class_destroy(dev_class);
	cdev_del(&cdev);
	unregister_chrdev_region(dev_num, 1);
	pr_info("chardev: /dev/%s removed\n", DEVICE_NAME);
}

module_init(chardev_init);
module_exit(chardev_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("NTU M266 Embedded Linux");
MODULE_DESCRIPTION("Character device driver demo for i.MX8MP EVK");
MODULE_VERSION("1.0");
