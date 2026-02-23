# 06 — References

This is the reference list I keep open in browser tabs more often than I'd like to admit. If you're working with the i.MX 8M Plus and Yocto, you'll probably end up bookmarking most of these too.

---

## NXP Official Documentation

### i.MX 8M Plus SoC

These three docs form the backbone of any low-level work on this chip.

| Doc Number | Title | What's In It |
|-----------|-------|--------------|
| IMX8MPLUSCEC | i.MX 8M Plus Applications Processor Datasheet | Full SoC datasheet — pinout, electrical specs, package info |
| IMX8MPLUSRM | i.MX 8M Plus Applications Processor Reference Manual | Register-level reference manual (5000+ pages — yes, really) |
| IMX8MPLUSHUG | i.MX 8M Plus Hardware Developer's Guide | Hardware design guidelines for custom boards |

You can find all of these under the **Documents** tab at:
<https://www.nxp.com/products/processors-and-microcontrollers/arm-processors/i-mx-applications-processors/i-mx-8-applications-processors/i-mx-8m-plus-arm-cortex-a53-machine-learning-vision-multimedia-and-industrial-iot:IMX8MPLUS>

### EVK Board

| Doc Number | Title | What's In It |
|-----------|-------|--------------|
| UG10164 | i.MX 8M Plus EVK Quick Start Guide | Getting started, DIP switch settings |
| UG10163 | i.MX 8M Plus EVK Board Hardware User's Guide | Detailed EVK hardware, connector pinouts |
| UG10166 | i.MX 8M Plus EVK Schematics | Full EVK schematics |

### Linux BSP

I've found myself going back to these constantly during BSP bring-up and driver work.

| Document | What's In It |
|----------|--------------|
| i.MX Yocto Project User's Guide | End-to-end Yocto BSP build instructions |
| i.MX Linux User's Guide | Linux drivers, multimedia, security subsystems |
| i.MX Linux Release Notes | BSP version info, known issues |
| i.MX Machine Learning User's Guide | eIQ ML framework usage |
| i.MX Porting Guide | Porting the BSP to a custom board |

### MCUXpresso SDK (Cortex-M7 Core)

| Document | What's In It |
|----------|--------------|
| MCUXpresso SDK API Reference Manual | Detailed SDK API docs |
| Getting Started with MCUXpresso SDK for EVK-MIMX8MP | M7 core development quickstart |
| MCUXpresso SDK Release Notes | SDK version info and changelog |

---

## GitHub Repositories

### NXP Official

These are the repos you'll need to clone (or at least browse) when building and customizing the BSP.

| Repo | What It Is | URL |
|------|-----------|-----|
| imx-manifest | Yocto BSP manifest (the `repo` entry point) | <https://github.com/nxp-imx/imx-manifest> |
| meta-imx | NXP i.MX Yocto meta-layer | <https://github.com/nxp-imx/meta-imx> |
| linux-imx | NXP i.MX Linux kernel fork | <https://github.com/nxp-imx/linux-imx> |
| uboot-imx | NXP i.MX U-Boot fork | <https://github.com/nxp-imx/uboot-imx> |
| imx-atf | ARM Trusted Firmware for i.MX | <https://github.com/nxp-imx/imx-atf> |
| mfgtools (UUU) | USB flashing tool | <https://github.com/nxp-imx/mfgtools> |
| mcux-sdk | MCUXpresso SDK core | <https://github.com/nxp-mcuxpresso/mcux-sdk> |
| mcux-sdk-examples | MCUXpresso SDK example code | <https://github.com/nxp-mcuxpresso/mcux-sdk-examples> |

### Yocto Project

| Repo | What It Is | URL |
|------|-----------|-----|
| poky | Yocto core (use the Scarthgap branch) | <https://git.yoctoproject.org/poky> |
| openembedded-core | OE-Core layer | <https://github.com/openembedded/openembedded-core> |
| meta-openembedded | Community layers collection | <https://github.com/openembedded/meta-openembedded> |

---

## Sensor Datasheets

| Sensor | Manufacturer | Datasheet |
|--------|-------------|-----------|
| BME280 | Bosch | <https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/> |
| MPU6050 | InvenSense (TDK) | <https://invensense.tdk.com/products/motion-tracking/6-axis/mpu-6050/> |
| SSD1306 | Solomon Systech | Search for "SSD1306 datasheet PDF" — plenty of copies floating around |
| OV5640 | OmniVision | Contact your supplier (NDA required) |

---

## Community Resources

### NXP Community Forum

When you're stuck on something i.MX-specific, this is the first place to search. NXP engineers do respond, though it can take a few days.

<https://community.nxp.com/t5/i-MX-Processors/bd-p/imx-processors>

### Yocto Community

- **Yocto Project Documentation** — the main reference: <https://docs.yoctoproject.org/>
- **Yocto Quick Build** — if you just want to get something building fast: <https://docs.yoctoproject.org/brief-yoctoprojectqs/index.html>
- **BitBake User Manual** — you'll need this once you start writing recipes: <https://docs.yoctoproject.org/bitbake/>

### FreeRTOS Community

- **FreeRTOS Documentation**: <https://www.freertos.org/Documentation/>
- **FreeRTOS API Reference**: <https://www.freertos.org/a00106.html>
- **FreeRTOS Source Code**: <https://github.com/FreeRTOS/FreeRTOS>

### TensorFlow Lite

- **TFLite Official**: <https://www.tensorflow.org/lite>
- **Model Optimization**: <https://www.tensorflow.org/lite/performance/model_optimization>

---

## Tutorials and Learning Materials

### Embedded Linux

These are the resources I keep coming back to. The Bootlin materials in particular are excellent — they're what training companies charge thousands of dollars for, but freely available as PDF slides and lab exercises.

| Resource | Type | URL |
|----------|------|-----|
| Bootlin Embedded Linux Training | Free slides + labs | <https://bootlin.com/training/embedded-linux/> |
| Bootlin Yocto Training | Free slides + labs | <https://bootlin.com/training/yocto/> |
| Linux Kernel Module Programming Guide | Online book | <https://sysprog21.github.io/lkmpg/> |
| Linux Device Drivers, 3rd Edition (LDD3) | Classic book (free online) | <https://lwn.net/Kernel/LDD3/> |

### RTOS

| Resource | Type | URL |
|----------|------|-----|
| Mastering the FreeRTOS Real Time Kernel | Official e-book | <https://www.freertos.org/Documentation/02-Kernel/07-Books-and-manual/01-RTOS_book> |
| FreeRTOS Kernel Features Tutorial | Official tutorial | <https://www.freertos.org/Documentation/02-Kernel/02-Kernel-features/00-Kernel-features> |

---

## Tools

| Tool | Purpose | Download |
|------|---------|----------|
| UUU | USB flashing (NXP boards) | <https://github.com/nxp-imx/mfgtools/releases> |
| MCUXpresso IDE | M7 development (optional) | <https://www.nxp.com/mcuxpresso> |
| VS Code | Code editor | <https://code.visualstudio.com/> |
| Wireshark | Network debugging | <https://www.wireshark.org/> |
| Saleae Logic | Logic analyzer software | <https://www.saleae.com/> |

---

## Quick-Reference Commands

### Linux Debugging

These are the commands I use most often when bringing up hardware on a new board.

```bash
# I2C
i2cdetect -y <bus>              # scan for devices on an I2C bus
i2cdump -y <bus> <addr>         # dump all registers from a device
i2cget -y <bus> <addr> <reg>    # read a single register
i2cset -y <bus> <addr> <reg> <value>  # write a single register

# SPI
ls /dev/spidev*                 # list available SPI devices
spidev_test -D /dev/spidev0.0  # loopback test

# GPIO
gpiodetect                      # list GPIO controllers
gpioinfo                        # show all GPIO lines and their state

# Device Tree
dtc -I fs /sys/firmware/devicetree/base  # decompile the live device tree

# Kernel Modules
lsmod                           # list loaded modules
modprobe <module>               # load a module
modinfo <module>                # show module info

# General Debug
dmesg | tail                    # recent kernel messages
cat /proc/interrupts            # interrupt counts per CPU
cat /proc/iomem                 # memory-mapped I/O regions
devmem2 <address> [type] [value]  # raw memory access (careful with this one)
```

### U-Boot

```
printenv                        # show all environment variables
setenv bootcmd '...'            # set the boot command
saveenv                         # persist env to storage

md 0x40000000 0x100             # memory display
mw 0x40000000 0xDEADBEEF       # memory write

dhcp                            # get IP via DHCP
tftp 0x40000000 zImage          # TFTP a kernel image
boot                            # execute bootcmd

# Loading M7 firmware from SD card
fatload mmc 1:1 0x7e0000 firmware.bin
bootaux 0x7e0000                # start the M7 core
```
