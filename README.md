# embedded-linux

An i.MX 8M Plus heterogeneous platform project: Yocto Linux on Cortex-A53 + FreeRTOS on Cortex-M7 + NPU edge inference.

I'm building this on the NXP i.MX 8M Plus EVK to explore the full stack of embedded Linux development — from writing kernel drivers and custom Yocto images, to real-time firmware on a dedicated MCU core, to deploying quantized neural networks on the onboard NPU. The goal is a working sensor platform where the A53 and M7 cores each do what they're good at.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   Cortex-A53 (Linux / Yocto)                                │
│   ├── Custom Yocto image (Scarthgap)                        │
│   ├── BME280 I2C kernel driver module                       │
│   ├── Userspace data collector daemon (C)                   │
│   ├── NPU inference — anomaly detection (eIQ / TFLite)     │
│   └── Lightweight web UI for live sensor data               │
│                                                              │
│                    ┌──────────────┐                          │
│                    │  RPMsg / MU  │                          │
│                    │ (inter-core) │                          │
│                    └──────────────┘                          │
│                                                              │
│   Cortex-M7 (FreeRTOS)                                      │
│   ├── MPU6050 6-axis real-time sampling (1 kHz)             │
│   ├── Hard real-time control loop                           │
│   ├── SSD1306 OLED local display                            │
│   └── Data packing + forwarding to A53 via RPMsg            │
│                                                              │
└──────────────────────────────────────────────────────────────┘

I2C buses:
  I2C3 (A53 Linux)  ──── BME280 (temp / humidity / pressure)
  I2C2 (M7 FreeRTOS) ─┬─ MPU6050 (accel / gyro)
                       └─ SSD1306 (OLED display)
```

The split is deliberate: environmental sensing (BME280) goes through a proper Linux kernel driver so I can expose it via sysfs and feed it into the NPU pipeline. Motion sensing (MPU6050) needs deterministic sub-millisecond timing, so it runs bare-metal on the M7 under FreeRTOS. The two cores talk over RPMsg through the Messaging Unit (MU) hardware.

## Hardware BOM

| Item | Part | Notes |
|------|------|-------|
| Dev board | 8MPLUSLPD4-EVK | i.MX 8M Plus EVK with LPDDR4 + eMMC |
| Camera adapter + OV5640 | MINISASTOCSI | MIPI CSI camera module |
| Industrial SD card | SDSDQAF4-032G-I | SanDisk industrial-grade |
| USB-UART cable | FTDI FT232RL 3.3V | For debug console |
| Temp/humidity/pressure sensor | BME280 (I2C, 3.3V) | Connected to I2C3 (A53 Linux) |
| 6-axis IMU | MPU6050 GY-521 | Connected to I2C2 (M7 FreeRTOS) |
| OLED display | SSD1306 0.96" I2C | Shares I2C2 bus with MPU6050 |

## Roadmap

### Phase 1 — Environment + first Yocto boot

- Set up Ubuntu 22.04 build host with all Yocto dependencies
- `repo init` the NXP BSP manifest, sync sources
- Build a minimal custom image with `bitbake`
- Flash to SD card, boot the EVK, get a serial console
- Verify basic peripherals (Ethernet, USB, eMMC)

### Phase 2 — Linux kernel driver development (BME280)

- Write an out-of-tree I2C kernel driver module for BME280
- Modify the device tree to describe the BME280 on I2C3
- Expose temperature, humidity, and pressure readings via sysfs
- Build a userspace data collector daemon in C
- Integrate the driver into the Yocto build as a recipe

### Phase 3 — FreeRTOS dual-core development (M7 + RPMsg)

- Set up the MCUXpresso SDK build environment for Cortex-M7
- Port or write a FreeRTOS application for MPU6050 sampling
- Bring up RPMsg communication between A53 (Linux) and M7 (FreeRTOS)
- Implement data packing on M7 and unpacking on the Linux side
- Add SSD1306 OLED output for local IMU status display

### Phase 4 — NPU edge AI integration

- Explore the eIQ ML framework and its TFLite delegate for the NPU
- Train and quantize a small anomaly detection model (INT8)
- Deploy on the NPU, feed it sensor data from both cores
- Build a lightweight web UI to display real-time data and inference results
- Profile NPU inference latency and power consumption

## Documentation

| Doc | Content |
|-----|---------|
| [01-dev-environment.md](docs/01-dev-environment.md) | Host PC setup: Ubuntu, Yocto deps, toolchains |
| [02-hardware-guide.md](docs/02-hardware-guide.md) | EVK unboxing, wiring, serial console, DIP switches |
| [03-yocto-bsp.md](docs/03-yocto-bsp.md) | Full Yocto build walkthrough (repo init to bitbake) |
| [04-freertos-m7.md](docs/04-freertos-m7.md) | Cortex-M7 FreeRTOS development (MCUXpresso SDK) |
| [05-npu-eiq.md](docs/05-npu-eiq.md) | NPU edge AI (eIQ, TFLite, quantized models) |
| [06-references.md](docs/06-references.md) | Official docs, community resources, useful links |

## Quick start

1. **Set up the build host** — Install Ubuntu 22.04 and the required packages. See [01-dev-environment.md](docs/01-dev-environment.md).
2. **Build the Yocto image** — Follow [03-yocto-bsp.md](docs/03-yocto-bsp.md) to `repo init`, sync, and `bitbake` a bootable image.
3. **Flash and boot** — Write the image to the industrial SD card, set the EVK's DIP switches to SD boot, and power on. You should get a login prompt over the FTDI serial cable.
4. **Wire up sensors** — Connect BME280 to I2C3 and MPU6050 + SSD1306 to I2C2. Pinout details in [02-hardware-guide.md](docs/02-hardware-guide.md).
5. **Build M7 firmware** — Compile the FreeRTOS application and load it onto the Cortex-M7. See [04-freertos-m7.md](docs/04-freertos-m7.md).

## License

MIT — see [LICENSE](LICENSE).
