# 02 — Hardware Guide

## EVK Unboxing Checklist

The 8MPLUSLPD4-EVK box should contain:

- [x] i.MX 8M Plus EVK main board (with LPDDR4 + eMMC)
- [x] 12 V / 5 A power adapter
- [x] USB-C cable (for USB OTG)
- [x] Quick Start Guide card
- [ ] **Not included** — serial cable. I bought an FTDI 3.3 V cable separately.
- [ ] **Not included** — SD card. I picked up an industrial-grade one.
- [ ] **Not included** — Ethernet cable. I'm using a spare from the lab.

## EVK Connector Map

### Key Connectors and Their Locations

| Ref | Connector | Notes |
|-----|-----------|-------|
| J23 | Micro USB (Debug UART) | **The most important connector for bring-up.** Plug this in and the on-board FTDI chip enumerates as 4 ttyUSB devices. |
| J21 | 40-pin expansion header | RPi-style GPIO header — used for sensors. |
| J6 | USB Type-C (OTG) | Image flashing via UUU / OTG mode. |
| J11 | USB 3.0 Type-A | External USB devices. |
| J7 | HDMI | Display output. |
| J10 | GbE RJ45 (1) | Ethernet port 1. |
| J11A | GbE RJ45 (2) | Ethernet port 2. |
| J801 | MIPI CSI | Camera input (needs MINISASTOCSI adapter board). |
| J3 | SD card slot | Boot from the SD card you've flashed. |
| SW4 | Boot Mode DIP switch | Selects the boot source. |
| SW1 | Power ON/OFF | Main power switch. |

## Boot Mode DIP Switch (SW4)

**Power off the board before touching the DIP switch!**

### SD Card Boot (day-to-day development)

| SW4[1] | SW4[2] | SW4[3] | SW4[4] |
|--------|--------|--------|--------|
| OFF | ON | OFF | OFF |

Use this for: first Yocto image boot, daily development and debugging.

### eMMC Boot (production)

| SW4[1] | SW4[2] | SW4[3] | SW4[4] |
|--------|--------|--------|--------|
| ON | OFF | OFF | OFF |

Use this for: final deployment to the on-board eMMC.

### Serial Download (USB flashing)

| SW4[1] | SW4[2] | SW4[3] | SW4[4] |
|--------|--------|--------|--------|
| OFF | OFF | OFF | OFF |

Use this for: flashing images over USB with the UUU tool.

> Reference: i.MX 8M Plus EVK Quick Start Guide (UG10164)

## Serial Console

### Physical Connection

1. Connect J23 (Micro USB Debug Port) to your host PC with a USB cable.
2. The on-board FTDI chip enumerates as **4 serial devices**.

### Serial Devices on the Linux Host

```
/dev/ttyUSB0 — Cortex-A53 UART (rarely used; depends on firmware revision)
/dev/ttyUSB1 — reserved
/dev/ttyUSB2 — **Cortex-A53 Linux console** (the one you want most of the time)
/dev/ttyUSB3 — **Cortex-M7 console** (FreeRTOS output)
```

> The actual numbers can shift if you already have other USB-serial adapters plugged in.
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

Connected to J801 through the MINISASTOCSI adapter board.

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

EVK J801 (MIPI CSI)
└──→ MINISASTOCSI adapter ──→ OV5640 camera
```

## Pre-Power-On Checklist

- [ ] Boot Mode DIP switch SW4 set to SD card mode
- [ ] SD card (with a flashed Yocto image) inserted into J3
- [ ] Debug USB cable connected from J23 to host PC
- [ ] Serial terminal open (115200 8N1)
- [ ] 12 V power adapter plugged in
- [ ] Sensor wiring double-checked (3.3 V only — don't connect 5 V!)

Press SW1 (Power). You should see U-Boot messages scrolling in your serial terminal.

## Next Step

Once the board is alive, move on to [03-Yocto-BSP.md](03-Yocto-BSP.md) to build a custom image.
