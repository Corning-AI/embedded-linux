# Edge AI on Embedded Linux — i.MX 8M Plus

Full-stack embedded Linux project on the NXP i.MX 8M Plus EVK — from Yocto BSP bring-up to real-time NPU object detection with live camera feed on HDMI.

## Demo

<p align="center">
  <a href="https://github.com/Corning-AI/embedded-linux/releases/latest">
    <img src="media/demo.gif" alt="Real-time object detection running on i.MX8MP NPU" width="480">
  </a>
</p>

Real-time object detection on the 2.3 TOPS NPU: OV5640 camera → MobileNet SSD v2 (INT8) → bounding boxes on HDMI, 11ms per inference, 9 FPS end-to-end. [Download full 68s demo video (25 MB)](https://github.com/Corning-AI/embedded-linux/releases/download/v0.3.0/imx8mp-edge-ai-demo.mov).

| | NPU | CPU | Speedup |
|---|-----|-----|---------|
| MobileNet SSD v2 (detection) | 11 ms | 45 ms | 4x |
| MoveNet Lightning (pose, 17 joints) | 13 ms | 26 ms | 2x |

```
OV5640 (MIPI-CSI2) → ISI DMA → GStreamer appsink → TFLite INT8 + VX Delegate → overlay → HDMI
  /dev/video3          zero-copy     numpy              NPU 11ms/frame          PIL      waylandsink
```

<table>
<tr>
<td width="33%" align="center">
<img src="media/demo-detection-3.jpg" width="240"><br>
<sub>3 objects detected simultaneously</sub>
</td>
<td width="33%" align="center">
<img src="media/demo-detection-2.jpg" width="240"><br>
<sub>NPU 11.3ms — stable across frames</sub>
</td>
<td width="33%" align="center">
<img src="media/demo-person-84.jpg" width="240"><br>
<sub>person 84% confidence</sub>
</td>
</tr>
</table>

## What's in this repo

```
app/camera-detect/         Detection + pose estimation app (Python, GStreamer, TFLite)
kernel-modules/
├── hello/                 Minimal loadable kernel module
├── chardev/               Character device with file_operations, ioctl, mutex
└── bme280/                I2C client driver with sysfs + device tree matching
drivers/v4l2-capture/      V4L2 multi-planar mmap capture (C)
scripts/as7263_display.py  NIR tissue monitor dashboard (GTK3 + Cairo, real-time)
scripts/as7263_monitor.py  NIR spectral sensor data logger (raw I2C, no dependencies)
dts/                       Device tree overlay for OV5640 camera pipeline
debug/                     Real debug cases from bring-up (with root cause)
scripts/                   Yocto build helper, serial file transfer
docs/                      Hardware guide, BSP build, WiFi/BT, camera+NPU, NIR sensor
```

## NIR Tissue Monitor

<p align="center">
  <img src="media/nir-demo.gif" alt="AS7263 NIR real-time tissue monitor on HDMI" width="480">
</p>

Real-time NIR spectral monitoring for cold therapy safety. AS7263 6-channel sensor (610–860 nm) reads tissue reflectance through on-board LED illumination, calculates a tissue oxygenation index (TOI), and displays live trends on HDMI via a full-screen GTK3 dashboard.

Tested with ice-pack cold stimulus on forearm skin — sensor detects vasoconstriction (S_680 drops 10%) and reactive hyperemia during rewarming (W_860 drops 17% as oxygen consumption surges). See [docs/10-nir-spectral-sensor.md](docs/10-nir-spectral-sensor.md) for full data.

```bash
# Run NIR dashboard on EVK (sensor on J21, LED auto-enabled)
python3 /opt/as7263_display.py
```

## Hardware

- NXP i.MX 8M Plus EVK (quad A53 + M7 + 2.3 TOPS NPU, 6 GB LPDDR4)
- OV5640 MIPI CSI-2 camera on J12
- AS7263 NIR spectral sensor on J21 (I2C3, 0x49)
- HDMI output on J17, Weston/Wayland
- AzureWave AW-CM276NF WiFi/BT (NXP 88W8997, PCIe + UART)
- Kernel 6.6.52-lts, Yocto Scarthgap

## Quick start

```bash
# Build Yocto image (Ubuntu 22.04 host, ~2h first time)
source scripts/build-multimedia.sh

# Flash SD (Rufus DD mode), boot switches SW4: OFF OFF ON ON
# Connect: USB-C → J5 (power), micro-USB → J23 (UART, 3rd COM port, 115200)

# Run detection demo on EVK
export XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1
python3 /opt/camera-detect/detect_camera.py --mode demo
```

## Detection app

```bash
python3 detect_camera.py                         # Object detection
python3 detect_camera.py --mode pose              # Pose estimation
python3 detect_camera.py --mode demo              # Both simultaneously
python3 detect_camera.py --mode demo --compare    # NPU vs CPU benchmark
python3 detect_camera.py --no-display             # Headless (serial/SSH)
```

Real-time OSD overlay with FPS, latency, object count. NMS post-processing, multi-model, Wayland output.

## Kernel modules

Three out-of-tree modules, each building on the previous:

- **hello** — `module_init`/`exit`, `printk`, `__init`/`__exit` sections
- **chardev** — full char device: `file_operations`, `copy_to_user`/`copy_from_user`, mutex, automatic `/dev` node
- **bme280** — I2C client driver: device tree matching, `i2c_smbus_*`, sysfs attributes, `devm_` managed alloc

## Debug log

Issues hit during bring-up, documented with root cause:

| Issue | Root cause |
|-------|-----------|
| `/dev/video0` is not the camera | VPU encoder grabs video0; camera = `/dev/video3` |
| Camera feed has red tint | ISI outputs BGR, code assumed RGB |
| `galcore` missing from `lsmod` | Built-in to kernel, not a loadable module |
| WiFi up but no DNS | `resolv.conf` empty, DHCP client didn't write it |
| Camera stream won't start | Need media-ctl link setup before streaming |
| `weston@root` service not found | Renamed to `weston.service` in Scarthgap |

## Progress

- [x] Yocto BSP build, SD boot
- [x] Camera: OV5640 → MIPI CSI-2 → ISI → GStreamer → HDMI preview
- [x] NPU: galcore + VX Delegate + TFLite INT8 verified
- [x] Kernel modules (hello → chardev → I2C)
- [x] V4L2 capture (C) + device tree overlay
- [x] WiFi (PCIe) + Bluetooth (UART)
- [x] Real-time detection: camera → NPU 11ms → overlay → HDMI
- [x] NIR spectral sensor: AS7263 bring-up, tissue monitoring, cold stimulus test
- [ ] FreeRTOS on M7 + RPMsg

## License

MIT
