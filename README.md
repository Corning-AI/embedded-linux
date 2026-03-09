# Embedded Linux on i.MX 8M Plus

Heterogeneous SoC platform project built on the NXP i.MX 8M Plus EVK. Covers BSP bring-up, kernel driver development, camera/NPU pipelines, and real-time co-processing with FreeRTOS on the Cortex-M7.

## Hardware

- **SoC:** NXP i.MX 8M Plus — quad Cortex-A53 (1.8 GHz) + Cortex-M7 + 2.3 TOPS NPU
- **Board:** 8MPLUSLPD4-EVK (6 GB LPDDR4, 32 GB eMMC)
- **Camera:** OV5640 MIPI CSI-2 via MINISASTOCSI adapter (J12)
- **Display:** HDMI 2.0a (J17), Weston/Wayland compositor
- **Kernel:** 6.6.52-lts (Yocto Scarthgap)

## Repository Structure

```text
kernel-modules/
├── hello/          Minimal loadable kernel module
├── chardev/        Character device driver (/dev node, ioctl, mutex)
└── bme280/         I2C client driver with sysfs interface

drivers/
└── v4l2-capture/   V4L2 mmap frame capture (C, multi-planar API)

dts/
└── imx8mp-evk-ov5640.dts   Annotated device tree overlay (camera pipeline)

debug/
├── 01-video-device-numbering   /dev/video0 is NOT the camera on i.MX8MP
├── 02-camera-red-tint          ISI RGB/BGR format mismatch → color shift
├── 03-galcore-not-in-lsmod     Built-in driver vs loadable module confusion
├── 04-wifi-dns-resolution      WiFi connected but no DNS → resolv.conf
├── 05-media-controller-pipeline  MC API graph setup for MIPI camera
└── 06-weston-service-name      Service renamed between Yocto releases

scripts/
├── build-multimedia.sh      Yocto build helper for imx-image-multimedia
└── serial_transfer.py       File transfer over debug UART (base64)

docs/
├── 01-dev-environment.md    Build host setup
├── 02-hardware-guide.md     EVK wiring, boot config, peripheral map
├── 03-yocto-bsp.md          Yocto BSP build (repo init → bitbake)
├── 07-camera-npu.md         Camera + NPU object detection pipeline
└── 08-device-tree-explained.md  Device tree walkthrough
```

## What's Working

| Subsystem | Status | Details |
| --------- | ------ | ------- |
| Yocto BSP | Boots from SD | `imx-image-multimedia`, Scarthgap branch |
| OV5640 camera | Live HDMI preview | MIPI CSI-2 → ISI → GStreamer → Weston |
| NPU (VIP8000) | Driver loaded | galcore 6.4.11, VX Delegate + TFLite 2.16.2 |
| GPU (GC7000UL) | Weston @ 60 FPS | `weston-simple-egl` verified |
| Debug UART | Working | J23, 3rd COM port = A53 console (115200 8N1) |

## Quick Start

```bash
# 1. Build the Yocto image (Ubuntu 22.04 host, ~2 hours first build)
source scripts/build-multimedia.sh

# 2. Flash to SD card (use Rufus DD image mode on Windows)
#    Set SW4: OFF OFF ON ON (SD card boot)

# 3. Connect: USB-C to J5 (power), micro-USB to J23 (debug UART)
#    Serial: 3rd COM port, 115200 8N1

# 4. Camera preview (on the EVK, over serial console)
export XDG_RUNTIME_DIR=/run/user/0
gst-launch-1.0 v4l2src device=/dev/video3 ! \
    video/x-raw,width=640,height=480,framerate=30/1 ! \
    videoconvert ! autovideosink

# 5. Build and load the hello module (cross-compile or on-device)
cd kernel-modules/hello
make ARCH=arm64 CROSS_COMPILE=aarch64-poky-linux- \
     KERNELDIR=/path/to/yocto/build/tmp/work/.../linux-imx/build
scp hello.ko root@<EVK_IP>:/tmp/
# On EVK:
insmod /tmp/hello.ko && dmesg | tail -3
```

## Kernel Modules

Three out-of-tree modules demonstrating progressive driver complexity:

**hello** — Module lifecycle (`init`/`exit`), `printk`, section markers (`__init`/`__exit`).

**chardev** — Full character device with dynamic major allocation, `file_operations` (read/write/ioctl), `copy_to_user`/`copy_from_user`, mutex synchronization, and automatic `/dev` node creation via `class_create`/`device_create`.

**bme280** — I2C client driver using the `probe`/`remove` lifecycle, device tree `compatible` matching, `i2c_smbus_*` register access, sysfs attributes, and `devm_` managed allocation.

## V4L2 Capture

Userspace C program demonstrating the V4L2 multi-planar API as used by i.MX8MP's ISI:

- `VIDIOC_QUERYCAP` → capability query
- `VIDIOC_S_FMT` → format negotiation (multi-planar)
- `VIDIOC_REQBUFS` + `mmap()` → zero-copy DMA buffer setup
- `VIDIOC_QBUF`/`VIDIOC_DQBUF` → streaming capture loop

## Device Tree

The [`dts/imx8mp-evk-ov5640.dts`](dts/imx8mp-evk-ov5640.dts) overlay is annotated to explain how the camera pipeline is described in hardware:

```text
OV5640 (I2C, 0x3c) → MIPI CSI-2 RX → ISI ch0 → /dev/video3
```

Covers clock providers, regulator bindings, OF graph endpoint linking, and MIPI lane configuration.

## i.MX8MP Video Device Map

On this SoC, `/dev/video0` is **not** the camera:

| Device | Function |
| ------ | -------- |
| /dev/video0 | VPU H.264/HEVC encoder |
| /dev/video1 | VPU decoder |
| /dev/video2 | ISI memory-to-memory (CSC) |
| /dev/video3 | **ISI capture (camera)** |

## Roadmap

- [x] Yocto BSP bring-up and first boot verification
- [x] Camera pipeline: OV5640 → ISI → GStreamer → HDMI
- [x] NPU stack verification (galcore, VX Delegate, TFLite)
- [x] Kernel module examples (hello, chardev, I2C driver)
- [x] V4L2 capture program and device tree overlay
- [ ] NPU benchmark: CPU vs NPU inference latency
- [ ] Real-time object detection (MobileNet SSD + camera + NPU)
- [ ] FreeRTOS on Cortex-M7 with RPMsg inter-core communication
- [ ] End-to-end demo: camera → NPU → overlay → HDMI

## License

MIT
