# 02 — Hardware Guide

## EVK Unboxing Checklist

The 8MPLUSLPD4-EVK box should contain:

- [x] i.MX 8M Plus EVK main board (with LPDDR4 6 GB + eMMC 32 GB)
- [x] USB Type-C 45 W PD power supply (5V/3A, 9V/3A, 15V/3A, 20V/2.25A)
- [x] USB-C cable (for USB 3.0 data)
- [x] USB micro-B cable (for debug UART J23)
- [x] USB Type-C to A adapter
- [x] Quick Start Guide card
- [ ] **Not included** — SD card (I'm using SanDisk 64 GB SDXC)
- [ ] **Not included** — HDMI display + cable
- [ ] **Not included** — Ethernet cable

## EVK Connector Map

### Key Connectors and Their Locations

| Ref | Connector | Notes |
|-----|-----------|-------|
| J5 | USB Type-C Port0 (Power) | **Power supply ONLY.** The only port for power delivery. |
| J6 | USB Type-C Port1 (USB 3.0) | USB data / UUU flashing. Not for power! |
| J23 | Micro USB (Debug UART) | **The most important connector for bring-up.** On-board FTDI enumerates as 4 serial ports. |
| J21 | 40-pin expansion header | RPi-style GPIO header — used for sensors. |
| J11 | USB 3.0 Type-A | External USB devices. |
| J17 | HDMI | Display output (HDMI 2.0a). |
| J10 | GbE RJ45 (1) | Ethernet port 1. |
| J11A | GbE RJ45 (2) | Ethernet port 2 (with TSN). |
| J12 | CSI1 MIPI | Camera input 1 (mini-SAS, needs MINISASTOCSI adapter). |
| J13 | CSI2 MIPI | Camera input 2 (mini-SAS, second camera slot). |
| J10 | M.2 Key-E (Wi-Fi/BT) | AW-CM276NF (88W8997) on PCIE-UART carrier board. |
| J3 | MicroSD card slot (bottom) | Boot from the SD card you've flashed. |
| SW4 | Boot Mode DIP switch | Selects the boot source (see table below). |
| SW3 | Power ON/OFF | Main power switch (slide to ON). |

## Boot Mode DIP Switch (SW4)

**Power off the board before touching the DIP switch!**

### Boot Device Settings (from NXP QSG, 1=ON 0=OFF)

| Boot Device | SW4-1 | SW4-2 | SW4-3 | SW4-4 | Use Case |
|-------------|-------|-------|-------|-------|----------|
| Boot From Fuses | OFF | OFF | OFF | OFF | Factory default |
| USB Serial Download | OFF | OFF | OFF | ON | UUU flashing |
| **eMMC (USDHC3)** | OFF | OFF | ON | OFF | Production (default from NXP) |
| **SD Card (USDHC2)** | **OFF** | **OFF** | **ON** | **ON** | **Day-to-day development** |
| NAND | OFF | ON | OFF | OFF | NAND flash boot |
| QSPI 3B Read | OFF | ON | ON | OFF | QSPI NOR boot |
| ecSPI Boot | ON | OFF | OFF | OFF | SPI boot |

> Reference: i.MX 8M Plus EVK Quick Start Guide (8MPLUSEVKQSG), Table 4

## Serial Console

### Physical Connection

1. Connect J23 (Micro USB Debug Port) to your host PC with a USB cable.
2. The on-board FTDI chip enumerates as **4 serial devices**.

### Serial Devices

The FTDI chip on J23 registers **4 serial ports**. The third port is the A53 Linux console, the fourth is M7.

**Windows (Device Manager → Ports):**

```
COM3 — Port 1 (not used)
COM4 — Port 2 (not used)
COM5 — **Cortex-A53 Linux console** ← use this
COM6 — **Cortex-M7 console** (FreeRTOS output)
```

> COM numbers may shift if other USB-serial devices are plugged in. Check Device Manager.

**Linux Host:**

```
/dev/ttyUSB0 — Port 1
/dev/ttyUSB1 — Port 2
/dev/ttyUSB2 — **Cortex-A53 Linux console** ← use this
/dev/ttyUSB3 — **Cortex-M7 console** (FreeRTOS output)
```

> Run `dmesg | grep ttyUSB` to confirm.

### Serial Parameters

```
Baud rate : 115200
Data bits : 8
Stop bits : 1
Parity    : None
Flow ctrl : None
```

### Connecting

```bash
# Pick whichever tool you prefer:
picocom -b 115200 /dev/ttyUSB2
minicom -D /dev/ttyUSB2 -b 115200
screen /dev/ttyUSB2 115200

# Exit shortcuts:
#   picocom  → Ctrl+A Ctrl+X
#   minicom  → Ctrl+A X
#   screen   → Ctrl+A K
```

### Permissions

If you get "permission denied", add yourself to the `dialout` group and re-login:

```bash
sudo usermod -aG dialout $USER
```

## External FTDI Cable Notes

If you need a second serial port — say, to watch M7 output at the same time — you can hook up a standalone FTDI cable to J21.

**Use a 3.3 V FTDI cable! A 5 V cable will fry the i.MX 8M Plus GPIOs.**

| FTDI Wire Color | Signal | EVK Pin |
|-----------------|--------|---------|
| Black | GND | J21 Pin 6 (GND) |
| Orange | TXD | J21 Pin 8 (UART_RXD) |
| Yellow | RXD | J21 Pin 10 (UART_TXD) |

> TXD goes to RXD, RXD goes to TXD — cross-connect!

## Sensor Wiring

### BME280 (Temperature / Humidity / Pressure) on I2C3 — driven by the A53 Linux kernel

| BME280 Pin | EVK J21 Pin | Function |
|------------|-------------|----------|
| VIN / VCC | Pin 1 (3.3V) | Power |
| GND | Pin 6 (GND) | Ground |
| SCL | Pin 5 (I2C3_SCL) | I2C clock |
| SDA | Pin 3 (I2C3_SDA) | I2C data |

Default I2C address: `0x76` (SDO tied to GND) or `0x77` (SDO tied to VCC).

### MPU6050 (6-Axis IMU) on I2C2 — sampled in real time by the M7 core

| MPU6050 Pin | EVK J21 Pin | Function |
|-------------|-------------|----------|
| VCC | Pin 1 (3.3V) | Power |
| GND | Pin 6 (GND) | Ground |
| SCL | Pin 28 (I2C2_SCL) or SPI | I2C/SPI clock |
| SDA | Pin 27 (I2C2_SDA) or SPI | I2C/SPI data |
| INT | Any free GPIO | Interrupt output |

I2C address: `0x68` (AD0 tied to GND) or `0x69` (AD0 tied to VCC).

### SSD1306 OLED Display on I2C — driven by the M7 core

| SSD1306 Pin | EVK J21 Pin | Function |
|-------------|-------------|----------|
| VCC | Pin 1 (3.3V) | Power |
| GND | Pin 6 (GND) | Ground |
| SCL | Shared with MPU6050 | I2C clock |
| SDA | Shared with MPU6050 | I2C data |

I2C address: `0x3C`.

### OV5640 Camera Module

Connected to **J12** (CSI1 MIPI) or **J13** (CSI2 MIPI) through the MINISASTOCSI adapter board and mini-SAS cable. Use J12 by default (matches the default device tree).

## Wiring Overview

```
EVK J21 40-pin Header
┌──────────────────────────────────────────────────────────────┐
│ Pin 1  (3.3V)     ──→ BME280 VCC, MPU6050 VCC, SSD1306 VCC  │
│ Pin 3  (I2C3_SDA) ──→ BME280 SDA                            │
│ Pin 5  (I2C3_SCL) ──→ BME280 SCL                            │
│ Pin 6  (GND)      ──→ ALL GND                               │
│ Pin 27 (I2C2_SDA) ──→ MPU6050 SDA, SSD1306 SDA              │
│ Pin 28 (I2C2_SCL) ──→ MPU6050 SCL, SSD1306 SCL              │
│ ...                                                          │
└──────────────────────────────────────────────────────────────┘

EVK J12 (CSI1 MIPI) — mini-SAS connector
└──→ mini-SAS cable ──→ MINISASTOCSI adapter ──→ OV5640 camera
```

## Pre-Power-On Checklist

- [ ] Boot Mode DIP switch SW4 set to SD card mode (`OFF OFF ON ON`)
- [ ] SD card (with a flashed Yocto image) inserted into J3 (bottom of board)
- [ ] Debug USB cable (micro-B) connected from J23 to host PC
- [ ] Serial terminal open on **3rd COM port** (115200 8N1) — COM5 on Windows, /dev/ttyUSB2 on Linux
- [ ] USB-C 45W PD power supply plugged into **J5** (NOT J6!)
- [ ] Sensor wiring double-checked (3.3 V only — don't connect 5 V!)

Slide **SW3** to ON. You should see U-Boot messages scrolling in your serial terminal within 1 second.

## First Boot Verification (2026-03-09)

Verified after first successful SD card boot with NXP Yocto scarthgap image.

### CPU — 4x Cortex-A53

```
$ cat /proc/cpuinfo
processor       : 0–3
BogoMIPS        : 16.00
Features        : fp asimd evtstrm aes pmull sha1 sha2 crc32 cpuid
CPU implementer : 0x41 (ARM)
CPU architecture: 8
CPU part        : 0xd03 (Cortex-A53)
CPU revision    : 4
```

All 4 cores online. Hardware crypto extensions (AES, SHA1, SHA2) available.

### Memory — 5.5 GiB usable (of 6 GB LPDDR4)

```
$ free -h
               total        used        free      shared  buff/cache   available
Mem:           5.5Gi       266Mi       5.2Gi        10Mi       161Mi       5.2Gi
Swap:             0B          0B          0B
```

~500 MB reserved by kernel (CMA, reserved memory regions for M7/VPU/GPU). No swap configured.

### Storage

```bash
$ lsblk
NAME         MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
mtdblock0     31:0    0    32M  0 disk                          ← SPI NOR Flash
mmcblk2      179:0    0  29.1G  0 disk                          ← eMMC (on-board)
├─mmcblk2p1  179:1    0  83.2M  0 part /run/media/boot-mmcblk2p1
└─mmcblk2p2  179:2    0   3.5G  0 part /run/media/root-mmcblk2p2
mmcblk1      179:96   0  59.5G  0 disk                          ← SD card (boot)
├─mmcblk1p1  179:97   0 332.8M  0 part /run/media/boot-mmcblk1p1
└─mmcblk1p2  179:98   0   1.8G  0 part /                        ← rootfs
```

- **SD card** (`mmcblk1`): 59.5 GB SanDisk SDXC, root filesystem on p2
- **eMMC** (`mmcblk2`): 29.1 GB on-board, factory image auto-mounted
- **SPI NOR** (`mtdblock0`): 32 MB, stores U-Boot backup

### Network

```bash
$ ip addr
eth0: <NO-CARRIER> mtu 1500  MAC 00:04:9f:09:74:df  state DOWN   ← FEC (J10)
eth1: <NO-CARRIER> mtu 1500  MAC 00:04:9f:09:74:e0  state DOWN   ← DWMAC (J11A, TSN)
can0: state DOWN                                                   ← CAN bus
```

Both Ethernet interfaces detected but no cable connected (state DOWN). **Wi-Fi/BT module present** — see [06-wifi-bluetooth.md](06-wifi-bluetooth.md) for setup.

### I2C Buses

```bash
$ i2cdetect -l
i2c-0   30a20000.i2c   ← I2C1 (PMIC, board management)
i2c-1   30a30000.i2c   ← I2C2 (for M7: MPU6050 + SSD1306)
i2c-2   30a40000.i2c   ← I2C3 (for A53: BME280)
i2c-6   DesignWare HDMI ← HDMI DDC
```

Hardware-to-Linux bus mapping:

| Hardware Bus | Linux Device | Base Address | Project Use |
| ------------ | ------------ | ------------ | ----------- |
| I2C1 | `i2c-0` | 0x30A20000 | Board management (PMIC, etc.) |
| I2C2 | `i2c-1` | 0x30A30000 | M7 FreeRTOS — MPU6050 + SSD1306 |
| I2C3 | `i2c-2` | 0x30A40000 | A53 Linux — BME280 sensor |
| HDMI DDC | `i2c-6` | — | HDMI EDID (automatic) |

> **Note:** I2C2 (`i2c-1`) is currently managed by Linux. When the M7 core takes over for FreeRTOS, this bus must be disabled in the Linux device tree to avoid bus contention.

### Phase 2 Readiness (2026-03-09)

```bash
$ uname -a
Linux imx8mpevk 6.6.52-lts-next-g5a0a5e71d2bd #1 SMP PREEMPT aarch64 GNU/Linux

$ ls /lib/modules/$(uname -r)/
kernel/ modules.alias modules.builtin modules.dep modules.order updates/ ...

$ which i2cdetect i2cdump i2cget i2cset
/usr/sbin/i2cdetect
/usr/sbin/i2cdump
/usr/sbin/i2cget
/usr/sbin/i2cset

$ i2cdetect -y 2    (I2C3 bus scan)
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- UU -- -- -- -- --
20: UU -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
40: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
50: 50 -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
70: -- -- -- -- -- -- -- --

$ cat /sys/class/remoteproc/remoteproc0/state
offline
```

I2C3 bus devices already present on the EVK:

| Address | Device | Status |
| ------- | ------ | ------ |
| 0x1a | WM8960 audio codec | `UU` (kernel driver bound) |
| 0x20 | PCA9535 GPIO expander | `UU` (kernel driver bound) |
| 0x50 | EEPROM | Unbound (available for raw access) |

All I2C tools available. Kernel module directory intact. Remoteproc offline and ready for M7 firmware loading.

### Available Sensors On Hand

| Sensor | Type | I2C Address | Planned Use |
| ------ | ---- | ----------- | ----------- |
| ADXL345 | 3-axis accelerometer | 0x53 or 0x1D | Phase 2 stand-in for BME280 (I2C driver practice) |
| SSD1306 | 0.96" OLED display | 0x3C | Phase 3 — M7 FreeRTOS local display |

> **Note:** BME280 and MPU6050 are on order. ADXL345 can be used to prototype the Phase 2 I2C kernel driver workflow while waiting for parts. Female-to-female jumper wires are needed to connect modules to J21.

## Next Step

Once the board is alive, move on to [03-Yocto-BSP.md](03-Yocto-BSP.md) to build a custom image.
