# 03 — Yocto BSP Build for i.MX 8M Plus

## What This Covers

NXP ships a Yocto Project-based BSP (Board Support Package) for their i.MX family. Building a custom Linux image with Yocto is the bread and butter of embedded Linux work — you'll spend a lot of time here.

I'm using **Scarthgap (Yocto 5.0)** with **NXP BSP release imx-6.6.52-2.2.2** (kernel 6.6.52).

## Prerequisites

- Everything in [01-dev-environment.md](01-dev-environment.md) is done
- At least **250 GB** of free disk space (not kidding — Yocto eats disk for breakfast)
- A stable internet connection for the initial source fetch

## Step 1: Initialize the Repo

NXP uses Google's `repo` tool to manage the many Yocto layers that make up the BSP.

```bash
mkdir -p ~/imx-yocto-bsp && cd ~/imx-yocto-bsp
repo init -u https://github.com/nxp-imx/imx-manifest \
    -b imx-linux-scarthgap \
    -m imx-6.6.52-2.2.2.xml
repo sync -j$(nproc)
```

The first `repo sync` pulls roughly **10 GB** of sources. Go grab a coffee.

## Step 2: Initialize the Build Environment

```bash
DISTRO=fsl-imx-xwayland MACHINE=imx8mpevk source imx-setup-release.sh -b build-xwayland
```

This script sets up the Yocto build directory, accepts the EULA, and drops you into `build-xwayland/`.

### Choosing a DISTRO

| DISTRO               | Display Stack    | When to Use                          |
|----------------------|------------------|--------------------------------------|
| `fsl-imx-xwayland`  | X11 + Wayland    | **Recommended** — most versatile     |
| `fsl-imx-wayland`   | Pure Wayland     | Leaner, no X11 compatibility layer   |
| `fsl-imx-fb`        | Framebuffer only | Headless / minimal systems, no GPU   |

I chose `fsl-imx-xwayland` because it covers the widest range of use cases. If you're running headless, `fsl-imx-fb` will save you build time and image size.

### Choosing a MACHINE

| MACHINE                | Hardware                            |
|------------------------|-------------------------------------|
| `imx8mpevk`           | i.MX 8M Plus EVK (LPDDR4)          |
| `imx8mp-lpddr4-evk`  | Same board — some BSP versions use this name instead |

If one doesn't work, try the other. NXP has renamed these across releases.

## Step 3: Customize the Build (Optional)

Edit `conf/local.conf` inside your build directory:

```bash
# Tune parallelism to your machine
BB_NUMBER_THREADS = "8"
PARALLEL_MAKE = "-j 8"

# Extra packages I find useful during development
IMAGE_INSTALL:append = " \
    i2c-tools \
    spidev-test \
    devmem2 \
    nano \
    openssh-sftp-server \
    python3 \
    python3-pip \
"

# NXP's ML package group (TensorFlow Lite, ONNX Runtime, etc.)
IMAGE_INSTALL:append = " packagegroup-imx-ml"
```

Note the space before the first package name in `IMAGE_INSTALL:append` — it's required. Yocto literally appends the string, so without the leading space you'll get `previous-pkgi2c-tools` and a confusing error.

## Step 4: Build

Pick the image that fits your needs:

```bash
# Minimal console image
bitbake imx-image-core

# Full image with GUI, multimedia, ML
bitbake imx-image-full

# Multimedia without the full desktop stack
bitbake imx-image-multimedia
```

I usually start with `imx-image-core` to verify the basic BSP works, then move to `imx-image-full` when I need the GPU/VPU/NPU stack.

### Build Time Expectations

| Hardware               | First Build   | Incremental Build |
|------------------------|---------------|-------------------|
| 8 cores / 16 GB / SSD | ~3–5 hours    | ~10–30 minutes    |
| 4 cores / 8 GB / HDD  | ~8–12 hours   | ~30–60 minutes    |

First builds are painful. After that, Yocto's `sstate-cache` makes incremental rebuilds much faster.

## Step 5: Flash an SD Card

Build artifacts land in:

```
build-xwayland/tmp/deploy/images/imx8mpevk/
```

You'll see `.wic` files — these are full disk images with partition tables already laid out.

### Option A: dd (the classic)

```bash
lsblk                          # identify your SD card — be careful here
sudo dd if=imx-image-core-imx8mpevk.wic \
    bs=4M conv=fsync status=progress \
    of=/dev/sdX
sudo sync
```

**Double-check `/dev/sdX`.** Writing to the wrong device will ruin your day.

### Option B: bmaptool (faster, recommended)

`bmaptool` only writes the non-empty blocks, so it's significantly faster than `dd` for sparse images.

```bash
sudo apt install bmap-tools
sudo bmaptool copy imx-image-core-imx8mpevk.wic /dev/sdX
```

### Option C: UUU (flash to eMMC over USB)

NXP's Universal Update Utility can flash directly to the on-board eMMC via USB OTG:

```bash
sudo uuu -b sd_all \
    imx-boot-imx8mpevk-sd.bin-flash_evk \
    imx-image-core-imx8mpevk.wic
```

This requires the board to be in serial download mode (check your DIP switch settings).

## Step 6: First Boot

1. Insert the SD card into the EVK at **J3**
2. Set DIP switch **SW4** to SD card boot mode
3. Connect a USB cable to the debug UART at **J23**
4. Open a serial terminal:
   ```bash
   picocom -b 115200 /dev/ttyUSB2
   ```
5. Press **SW1** to power on

### What You Should See

```
[U-Boot]
U-Boot 2024.04-... (NXP i.MX8MP)
Hit any key to stop autoboot:

[Linux kernel]
Starting kernel ...

[login prompt]
imx8mpevk login: root
```

Default login is `root` with no password.

### Post-Boot Sanity Checks

Run through these to make sure the basics are working:

```bash
# Kernel version
uname -a

# CPU info — should show 4x Cortex-A53
cat /proc/cpuinfo

# Memory — expect ~2 GB usable on a 2 GB LPDDR4 board
free -h

# I2C buses — verifies the I2C subsystem is up
i2cdetect -l

# Network
ifconfig eth0

# NPU (if using imx-image-full)
cat /sys/class/misc/vsi_vip/instance_num
```

If any of these look wrong, check the serial console output for errors during boot.

## Common Build Errors and Fixes

### 1. do_fetch Failure — Download Timeout

Yocto fetches sources from upstream during the build. If your network is flaky or a mirror is down, `do_fetch` will fail.

**Fix:** Set up a proxy, or manually download the tarball and drop it into the `downloads/` directory in your build folder. Yocto will find it there and skip the fetch.

### 2. do_compile Failure — Out of Memory

The telltale sign:

```
internal compiler error: Killed (program cc1plus)
```

The kernel OOM-killer is terminating the compiler. You don't have enough RAM for the parallelism you've configured.

**Fix:** Reduce `BB_NUMBER_THREADS` and `PARALLEL_MAKE` in `local.conf`, or add swap:

```bash
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

To make it permanent, add an entry to `/etc/fstab`.

### 3. Locale Errors

See [01-dev-environment.md](01-dev-environment.md) — the fix is setting up `en_US.UTF-8`.

### 4. Disk Space Exhausted

Yocto builds are huge. If you run out of space mid-build:

```bash
# Remove old shared-state cache entries
cd ~/imx-yocto-bsp/build-xwayland
# Check what's eating space
du -sh sstate-cache/ tmp/
```

You can safely delete `sstate-cache/` — it'll just make the next build slower. The `tmp/` directory holds all build artifacts and can also be wiped, but you'll need a full rebuild.

### 5. MACHINE Name Not Recognized

NXP has used different machine names across BSP releases. If `imx8mpevk` gives you an error like "MACHINE is not defined", try `imx8mp-lpddr4-evk` instead (or vice versa). Check the BSP release notes for the correct name.

## Creating a Custom Meta-Layer

Once you move beyond basic image customization, you'll want your own Yocto layer. This keeps your changes separate from NXP's sources and makes them easier to version-control.

### Create the Layer Skeleton

```bash
cd ~/imx-yocto-bsp/sources
bitbake-layers create-layer meta-imx8mp-custom
```

### Typical Layer Structure

```
meta-imx8mp-custom/
├── conf/
│   └── layer.conf
├── recipes-kernel/
│   └── linux/
│       └── linux-imx_%.bbappend        # kernel config tweaks, patches
├── recipes-bsp/
│   └── device-tree/
│       └── imx8mp-custom-dt.bb         # custom device tree overlays
└── recipes-app/
    └── sensor-app/
        └── sensor-app_1.0.bb           # your application recipe
```

- **`.bbappend` files** modify existing recipes (e.g., adding kernel config fragments or patches to the NXP kernel)
- **`.bb` files** define new recipes (e.g., your own application)

### Add the Layer to Your Build

```bash
bitbake-layers add-layer ../sources/meta-imx8mp-custom
```

This modifies `conf/bblayers.conf` in your build directory. You can also edit that file by hand if you prefer.

After adding the layer, run `bitbake-layers show-layers` to confirm it's picked up.
