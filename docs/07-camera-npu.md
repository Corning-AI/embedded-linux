# 07 — Camera + NPU: Real-time Edge AI Object Detection

## Goal

Build a real-time object detection demo using the OV5640 MIPI CSI camera, the onboard Verisilicon VIP8000 NPU (2.3 TOPS INT8), and an HDMI display. This showcases the full heterogeneous processing capability of the i.MX 8M Plus: Cortex-A53 Linux for application logic, NPU for inference acceleration, and Cortex-M7 FreeRTOS for real-time coordination.

<!-- 目标：用 OV5640 摄像头 + NPU 做实时物体检测，HDMI 显示结果，展示异构 SoC 全栈能力 -->

## Demo Architecture

```text
OV5640 Camera (MIPI CSI, J12)
    │
    ▼
ISI / V4L2 capture
    │
    ▼
GStreamer pipeline (frame acquisition)
    │
    ▼
TFLite + VX Delegate ──→ NPU (MobileNet SSD, INT8)
    │
    ▼
Overlay: bounding boxes + labels + FPS + NPU latency
    │
    ▼
Wayland/Weston ──→ HDMI Display (J7)

    ┌──────────────────────────────────────┐
    │  Cortex-M7 (FreeRTOS)               │
    │  └── heartbeat via RPMsg            │
    │      → shown on display overlay     │
    └──────────────────────────────────────┘
```

## HDMI Output Layout

```text
┌─────────────────────────────────────────────────────────┐
│  ┌───────────────────────────────────┐  ┌────────────┐  │
│  │                                   │  │ NPU: 8ms   │  │
│  │   Live Camera Feed               │  │ CPU: 180ms  │  │
│  │   + Bounding Boxes               │  │ FPS: 33     │  │
│  │   + Labels + Confidence          │  │             │  │
│  │                                   │  │ M7: alive   │  │
│  │   [phone 92%]  [cup 87%]         │  │ uptime: 42s │  │
│  │                                   │  └────────────┘  │
│  └───────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

## Skills Demonstrated

| Skill | How It's Shown |
| ----- | -------------- |
| Embedded Linux BSP | Custom Yocto image, kernel config, device tree |
| Camera / video pipeline | MIPI CSI → ISI → V4L2 → GStreamer |
| Hardware acceleration | TFLite + VX Delegate → NPU (2.3 TOPS) |
| Real-time systems | FreeRTOS on M7, hard real-time heartbeat |
| Inter-core communication | RPMsg between A53 (Linux) and M7 (FreeRTOS) |
| Performance engineering | CPU vs NPU benchmark, FPS optimization |
| System integration | End-to-end: camera → compute → display |

## Hardware

| Item | Connection | Notes |
| ---- | ---------- | ----- |
| OV5640 + MINISASTOCSI adapter | J12 (CSI1 MIPI) | Official NXP camera module; mini-SAS cable connection |
| HDMI display + cable | J7 | Any HDMI monitor |
| Ethernet cable | J10 or J11A | For file transfer (scp, wget) |

## Step-by-step

### Step 1 — Connect camera and display

1. Power off EVK (SW3 → OFF)
2. Connect OV5640 camera to **J12** (CSI1 MIPI) via MINISASTOCSI adapter
   - Use the mini-SAS cable (included with the MINISASTOCSI kit)
   - Plug into J12 until the latch clicks
3. Connect HDMI cable from **J7** to display
4. Connect Ethernet cable to **J10**
5. Power on, login as `root`

### Step 2 — Verify camera detection

```bash
dmesg | grep -i ov5640
ls /dev/video*
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Expected output: OV5640 detected on I2C1 (address 0x3c), `/dev/video0` created, supports YUYV/NV12 up to 1920x1080.

If `ov5640_check_chip_id: failed` appears, the camera isn't physically connected or the mini-SAS cable is loose.

### Step 3 — Test live preview on HDMI

```bash
# Camera → HDMI display
gst-launch-1.0 v4l2src device=/dev/video0 ! \
    video/x-raw,width=640,height=480,framerate=30/1 ! \
    waylandsink

# Alternative: NXP's optimized source element
gst-launch-1.0 imxv4l2src device=/dev/video0 ! \
    video/x-raw,width=640,height=480 ! \
    waylandsink
```

If Weston is not running: `systemctl start weston@root`

### Step 4 — Verify NPU stack

```bash
# NPU kernel driver
lsmod | grep galcore

# VX Delegate library
ls /usr/lib/libvx_delegate.so

# TFLite runtime
python3 -c "import tflite_runtime; print('TFLite OK')"

# Benchmark tool
ls /usr/bin/tensorflow-lite-*/tools/benchmark_model
```

### Step 5 — Get network access and download model

```bash
# DHCP on eth0
dhclient eth0 && ip addr show eth0

# Create directories
mkdir -p /opt/models /opt/camera-detect

# Download MobileNet SSD v1 (COCO dataset, INT8 quantized)
cd /opt/models
wget https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
unzip coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
```

If no internet on the board, download on PC and transfer:

```bash
scp detect.tflite root@<EVK_IP>:/opt/models/
```

### Step 6 — Benchmark NPU vs CPU

```bash
BENCH=/usr/bin/tensorflow-lite-*/tools/benchmark_model
MODEL=/opt/models/detect.tflite

# CPU-only inference
$BENCH --graph=$MODEL --num_runs=50 --warmup_runs=5

# NPU-accelerated inference
$BENCH --graph=$MODEL \
    --external_delegate_path=/usr/lib/libvx_delegate.so \
    --num_runs=50 --warmup_runs=5
```

Expected results:

| Backend | Inference Latency | Notes |
| ------- | ----------------- | ----- |
| CPU (A53) | ~180–200 ms | 4 threads |
| NPU (VX Delegate) | ~8–12 ms | INT8 quantized |
| Speedup | ~20x | |

### Step 7 — Check for NXP pre-built demos

```bash
find / -name "*eiq*" -o -name "*detection*" -o -name "*classify*" 2>/dev/null | head -20
gst-inspect-1.0 | grep -i tensor
ls /opt/gopoint* /usr/share/nxp* 2>/dev/null
```

NXP's Yocto image may ship demo applications we can adapt instead of writing from scratch.

### Step 8 — Build the detection application

Python script: `/opt/camera-detect/detect_camera.py`

Functionality:

1. Capture frames from OV5640 via V4L2 / GStreamer
2. Run MobileNet SSD on NPU via TFLite + VX Delegate
3. Draw bounding boxes, class labels, confidence scores
4. Overlay performance metrics: FPS, NPU vs CPU latency
5. Show M7 heartbeat status (from RPMsg)
6. Display on HDMI via Wayland

Key dependencies:

- `tflite_runtime` — inference with VX Delegate
- GStreamer Python (`gi.repository.Gst`) — camera capture + display
- `PIL` or `cv2` — drawing overlays

### Step 9 — Add M7 FreeRTOS heartbeat via RPMsg

On the Ubuntu build host, build the RPMsg echo example:

```bash
cd mcux-sdk-examples/boards/evkmimx8mp/multicore_examples/rpmsg_lite_str_echo_rtos/armgcc
export ARMGCC_DIR=/opt/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi
./build_release.sh
```

Transfer and load on the EVK:

```bash
cp rpmsg_lite_str_echo_rtos.elf /lib/firmware/
echo rpmsg_lite_str_echo_rtos.elf > /sys/class/remoteproc/remoteproc0/firmware
echo start > /sys/class/remoteproc/remoteproc0/state

# Verify
cat /sys/class/remoteproc/remoteproc0/state   # should say "running"
ls /dev/ttyRPMSG*                               # should see ttyRPMSG0
echo "ping" > /dev/ttyRPMSG0
cat /dev/ttyRPMSG0                              # should echo back
```

The detection application reads M7 status from `/dev/ttyRPMSG0` and displays it on the HDMI overlay.

### Step 10 — Record demo video

1. Run the detection app
2. Point camera at desk objects (phone, cup, keyboard, book)
3. Move objects to show real-time tracking
4. Record the HDMI display with a phone or capture card
5. Upload as GIF or video to the GitHub repo

### Step 11 — Document results

Update this file with:

- Actual benchmark numbers
- Screenshots / GIF of the running demo
- Any issues encountered and workarounds

## File locations

**On the EVK:**

| What | Path |
| ---- | ---- |
| Detection model | `/opt/models/detect.tflite` |
| COCO labels | `/opt/models/coco_labels.txt` |
| Detection app | `/opt/camera-detect/detect_camera.py` |
| VX Delegate | `/usr/lib/libvx_delegate.so` |
| M7 firmware | `/lib/firmware/rpmsg_lite_str_echo_rtos.elf` |

**In the repo:**

| What | Path |
| ---- | ---- |
| This document | `docs/07-camera-npu.md` |
| Detection app source | `app/camera-detect/detect_camera.py` |
| Model download script | `scripts/download_model.sh` |
| Demo video / GIF | `docs/assets/demo-detection.gif` |

## Troubleshooting

| Problem | Solution |
| ------- | -------- |
| OV5640 not detected | Re-seat mini-SAS cable on J12; check `dmesg` for I2C errors on bus 1 |
| No video on HDMI | `systemctl status weston`; re-seat HDMI adapter board |
| `waylandsink` fails | Try `fbdevsink` or run as root |
| OpenCV not available | Use GStreamer Python bindings; or rebuild Yocto with `opencv` |
| No internet for model download | Download on PC, `scp` to board |
| VX Delegate fails | Check `lsmod \| grep galcore`; try `modprobe galcore` |
| `/dev/ttyRPMSG*` missing | Check device tree rpmsg node and reserved memory regions |
