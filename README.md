# embedded-linux

An i.MX 8M Plus heterogeneous platform project: Yocto Linux on Cortex-A53 + FreeRTOS on Cortex-M7 + NPU edge inference.

<!-- 异构多核嵌入式 Linux 项目：A53 跑 Linux，M7 跑 FreeRTOS，NPU 做边缘推理 -->

I'm building this on the NXP i.MX 8M Plus EVK to explore the full stack of embedded Linux development — from writing kernel drivers and custom Yocto images, to real-time firmware on a dedicated MCU core, to deploying quantized neural networks on the onboard NPU. The goal is a working sensor platform where the A53 and M7 cores each do what they're good at.

## Current Status

**Phase 1 complete** — the EVK boots a custom Yocto scarthgap image from SD card. All core peripherals verified (CPU, RAM, storage, network interfaces, I2C buses). See the [first boot verification log](docs/02-hardware-guide.md#first-boot-verification-2026-03-09) for details.

<!-- 当前进度：Phase 1 已完成，EVK 已成功从 SD 卡启动自定义 Yocto 镜像。所有基本外设验证通过。 -->

| Milestone | Status |
| --------- | ------ |
| Phase 1 — Yocto first boot & peripheral verification | **Done** |
| Phase 2 — BME280 I2C kernel driver (A53 Linux) | Next up |
| Phase 3 — FreeRTOS on M7 + RPMsg inter-core comms | Planned |
| Phase 4 — NPU edge inference with eIQ / TFLite | Planned |

## Architecture

```text
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

<!-- 架构说明：环境传感（BME280）走 Linux 内核驱动，运动传感（MPU6050）走 M7 实时采样，两核通过 RPMsg 通信 -->

The split is deliberate: environmental sensing (BME280) goes through a proper Linux kernel driver so I can expose it via sysfs and feed it into the NPU pipeline. Motion sensing (MPU6050) needs deterministic sub-millisecond timing, so it runs bare-metal on the M7 under FreeRTOS. The two cores talk over RPMsg through the Messaging Unit (MU) hardware.

## Hardware

| Item | Part | Notes |
| ---- | ---- | ----- |
| Dev board | 8MPLUSLPD4-EVK | i.MX 8M Plus EVK, 6 GB LPDDR4, 32 GB eMMC |
| Camera adapter + OV5640 | MINISASTOCSI | MIPI CSI camera module |
| Industrial SD card | SanDisk SDXC 64 GB | SD boot for development |
| Temp/humidity/pressure sensor | BME280 (I2C, 3.3 V) | Connected to I2C3 (A53 Linux) |
| 6-axis IMU | MPU6050 GY-521 | Connected to I2C2 (M7 FreeRTOS) |
| OLED display | SSD1306 0.96" I2C | Shares I2C2 bus with MPU6050 |

### Verified Specs (from first boot)

<!-- 首次启动验证数据 -->

| Parameter | Value |
| --------- | ----- |
| CPU | 4x Cortex-A53 @ 1.8 GHz (ARMv8-A) |
| Usable RAM | 5.5 GiB (of 6 GB LPDDR4) |
| eMMC | 29.1 GB on-board |
| SPI NOR | 32 MB |
| Ethernet | 2x GbE (FEC + DWMAC/TSN) |
| I2C | 3 buses available (I2C1–I2C3) |
| Kernel | 6.6.52-lts (Yocto scarthgap) |

## Roadmap

### Phase 1 — Environment + first Yocto boot ✓

- [x] Set up Ubuntu 22.04 build host with all Yocto dependencies
- [x] `repo init` the NXP BSP manifest, sync sources
- [x] Build a minimal custom image with `bitbake`
- [x] Flash to SD card, boot the EVK, get a serial console
- [x] Verify basic peripherals (CPU, RAM, storage, network, I2C)

### Phase 2 — Linux kernel driver development (BME280)

- [ ] Write an out-of-tree I2C kernel driver module for BME280
- [ ] Modify the device tree to describe the BME280 on I2C3
- [ ] Expose temperature, humidity, and pressure readings via sysfs
- [ ] Build a userspace data collector daemon in C
- [ ] Integrate the driver into the Yocto build as a recipe

### Phase 3 — FreeRTOS dual-core development (M7 + RPMsg)

<!-- M7 实时核开发：MCUXpresso SDK + FreeRTOS + RPMsg 核间通信 -->

- [ ] Set up the MCUXpresso SDK build environment for Cortex-M7
- [ ] Port or write a FreeRTOS application for MPU6050 sampling at 1 kHz
- [ ] Bring up RPMsg communication between A53 (Linux) and M7 (FreeRTOS)
- [ ] Implement data packing on M7 and unpacking on the Linux side
- [ ] Add SSD1306 OLED output for local IMU status display

### Phase 4 — NPU edge AI integration

<!-- NPU 边缘推理：eIQ + TFLite + INT8 量化模型 -->

- [ ] Explore the eIQ ML framework and its TFLite delegate for the NPU
- [ ] Train and quantize a small anomaly detection model (INT8)
- [ ] Deploy on the NPU, feed it sensor data from both cores
- [ ] Build a lightweight web UI to display real-time data and inference results
- [ ] Profile NPU inference latency and power consumption

## Documentation

| Doc | Content |
| --- | ------- |
| [01-dev-environment.md](docs/01-dev-environment.md) | Host PC setup: Ubuntu, Yocto deps, toolchains |
| [02-hardware-guide.md](docs/02-hardware-guide.md) | EVK wiring, serial console, DIP switches, boot verification |
| [03-yocto-bsp.md](docs/03-yocto-bsp.md) | Full Yocto build walkthrough (repo init to bitbake) |
| [04-freertos-m7.md](docs/04-freertos-m7.md) | Cortex-M7 FreeRTOS development (MCUXpresso SDK) |
| [05-npu-eiq.md](docs/05-npu-eiq.md) | NPU edge AI (eIQ, TFLite, quantized models) |
| [06-references.md](docs/06-references.md) | Official docs, community resources, useful links |

## Quick Start

1. **Set up the build host** — Install Ubuntu 22.04 and the required packages. See [01-dev-environment.md](docs/01-dev-environment.md).
2. **Build the Yocto image** — Follow [03-yocto-bsp.md](docs/03-yocto-bsp.md) to `repo init`, sync, and `bitbake` a bootable image.
3. **Flash and boot** — Write the `.wic` image to SD card with Rufus (use DD image mode), set SW4 to `OFF OFF ON ON`, power on via J5. Login as `root` (no password) over the serial console at J23 (3rd COM port, 115200 8N1).
4. **Wire up sensors** — Connect BME280 to I2C3 and MPU6050 + SSD1306 to I2C2. Pinout details in [02-hardware-guide.md](docs/02-hardware-guide.md).
5. **Build M7 firmware** — Compile the FreeRTOS application and load it onto the Cortex-M7. See [04-freertos-m7.md](docs/04-freertos-m7.md).

<!-- 快速开始提示：烧录用 Rufus DD 模式，SW4 拨到 OFF OFF ON ON，串口选第三个 COM 口 -->

## License

MIT — see [LICENSE](LICENSE).
