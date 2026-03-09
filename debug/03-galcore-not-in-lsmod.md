# galcore not showing in lsmod but NPU works

## Problem

Following NXP documentation to verify the NPU driver:

```
root@imx8mpevk:~# lsmod | grep galcore
(empty)
```

No output. According to the docs this means the GPU/NPU driver isn't loaded. But the VX Delegate library exists and TFLite loads it without errors.

## Investigation

Checked if the device node exists:

```
root@imx8mpevk:~# ls /dev/galcore
/dev/galcore

root@imx8mpevk:~# dmesg | grep -i galcore
[    2.199130] Galcore version 6.4.11.p2.745085
```

The driver is loaded and initialized at boot. The device node exists. The version string appears in dmesg.

## Root cause

NXP's BSP builds galcore as a **built-in kernel module** (`obj-y`), not a loadable module (`obj-m`). Built-in drivers don't appear in `lsmod` because they're compiled directly into the vmlinux binary — there's no `.ko` file to track.

To confirm:

```
root@imx8mpevk:~# cat /lib/modules/6.6.52-lts/modules.builtin | grep galcore
(nothing — it's even more deeply integrated, compiled into the base kernel)
```

## Correct verification method

Don't rely on `lsmod`. Check for the device node and dmesg instead:

```bash
# Device node exists?
ls /dev/galcore

# Driver initialized?
dmesg | grep -i "galcore version"

# Specific parameter accessible?
cat /sys/module/galcore/parameters/gpuProfiler 2>/dev/null
```

## Takeaway

`lsmod` only shows loadable kernel modules (`.ko` files inserted via `insmod`/`modprobe`). Built-in drivers (`=y` in `.config`) are invisible to `lsmod`. This is a common source of confusion, especially on vendor BSPs where GPU/NPU drivers are often built-in for boot-time availability.
