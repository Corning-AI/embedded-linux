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
Wayland/Weston ──→ HDMI Display (J17)

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
| HDMI display + cable | J17 | Any HDMI monitor |
| Ethernet cable | J10 or J11A | For file transfer (scp, wget) |

## Step-by-step

### Step 1 — Connect camera and display

1. Power off EVK (SW3 → OFF)
2. Connect OV5640 camera to **J12** (CSI1 MIPI) via MINISASTOCSI adapter
   - Use the mini-SAS cable (included with the MINISASTOCSI kit)
   - Plug into J12 until the latch clicks
3. Connect HDMI cable from **J17** to display
4. Connect Ethernet cable to **J10**
5. Power on, login as `root`

### Step 2 — Verify camera detection

```bash
dmesg | grep -i ov5640
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video3 --list-formats-ext
```

**IMPORTANT:** On i.MX8MP, the video device numbering is:

| Device | Function | Notes |
| ------ | -------- | ----- |
| `/dev/video0` | VPU encoder (vsi_v4l2enc) | H.264/HEVC encoding, NOT camera! |
| `/dev/video1` | VPU decoder (vsi_v4l2dec) | H.264/HEVC decoding |
| `/dev/video2` | ISI M2M (mxc-isi-m2m_v1) | Color space conversion |
| `/dev/video3` | **ISI Capture (mxc-isi-cap_v1)** | **This is the camera!** |

Verified output (2026-03-10):

```
[    0.080573] platform 32e40000.csi: Fixed dependency cycle(s) with /soc@0/bus@30800000/i2c@30a30000/ov5640_mipi@3c
[    2.633919] ov5640 1-003c: supply DOVDD not found, using dummy regulator
[    8.525147] mx8-img-md: Registered sensor subdevice: ov5640 1-003c (1)
[    8.548408] mx8-img-md: created link [ov5640 1-003c] => [mxc-mipi-csi2.0]
```

OV5640 detected at I2C address 0x3c, linked to MIPI CSI-2 receiver. The "supply not found, using dummy regulator" warnings are normal — the EVK uses fixed regulators not described in the device tree.

If `ov5640_check_chip_id: failed` appears, the camera isn't physically connected or the mini-SAS cable is loose.

### Step 3 — Test live preview on HDMI

```bash
# Camera → HDMI display (use /dev/video3, NOT video0!)
gst-launch-1.0 v4l2src device=/dev/video3 ! \
    video/x-raw,width=640,height=480,framerate=30/1 ! \
    waylandsink

# Alternative: NXP's optimized source element
gst-launch-1.0 imxv4l2src device=/dev/video3 ! \
    video/x-raw,width=640,height=480 ! \
    waylandsink
```

If Weston is not running: `systemctl start weston.service`

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

WiFi is available via `mlan0` (see [06-wifi-bluetooth.md](06-wifi-bluetooth.md)), or use Ethernet.

```bash
mkdir -p /opt/models /opt/camera-detect

# Download MobileNet SSD v1 (COCO dataset, INT8 quantized)
cd /opt/models
wget https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
unzip coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
```

If long URLs get corrupted via serial, download on PC and transfer via WiFi:

```bash
# On Windows host:
scp ssd_model.zip root@192.168.1.98:/opt/models/
# On EVK:
cd /opt/models && unzip ssd_model.zip
```

Model files: `detect.tflite` (4.2 MB) + `labelmap.txt` (COCO 90 classes).

### Step 6 — Benchmark NPU vs CPU

> **Note:** `benchmark_model` is not included in `imx-image-multimedia`. Use Python instead:

```python
import time, numpy as np
import tflite_runtime.interpreter as tflite

MODEL = "/opt/models/detect.tflite"

# CPU benchmark
interp_cpu = tflite.Interpreter(model_path=MODEL, num_threads=4)
interp_cpu.allocate_tensors()
inp = interp_cpu.get_input_details()
dummy = np.random.randint(0, 255, size=inp[0]["shape"], dtype=np.uint8)
# ... warmup + timing loop ...

# NPU benchmark
delegate = tflite.load_delegate("/usr/lib/libvx_delegate.so")
interp_npu = tflite.Interpreter(model_path=MODEL, experimental_delegates=[delegate])
# ... same warmup + timing loop ...
```

Verified results (2026-03-10, MobileNet SSD v1 INT8, 300x300 input):

| Backend | Avg Latency | Min | Max | Notes |
| ------- | ----------- | --- | --- | ----- |
| CPU (A53 x4, XNNPACK) | **45.3 ms** | 45.2 | 45.5 | NEON SIMD auto-enabled |
| NPU (VX Delegate) | **9.1 ms** | 8.5 | 9.7 | 1 op fallback to CPU (PostProcess) |
| Speedup | **5.0x** | | | CPU faster than expected due to XNNPACK |

> **Note:** CPU is faster than initial estimates (~45ms vs ~180ms) because TFLite 2.16's XNNPACK delegate uses ARM NEON SIMD on the A53. The NPU's real advantage is **freeing CPU for other tasks** (camera capture, display, post-processing) in a concurrent pipeline.

### Step 7 — Check for NXP pre-built demos

```bash
find / -name "*eiq*" -o -name "*detection*" -o -name "*classify*" 2>/dev/null | head -20
gst-inspect-1.0 | grep -i tensor
ls /opt/gopoint* /usr/share/nxp* 2>/dev/null
```

NXP's Yocto image may ship demo applications we can adapt instead of writing from scratch.

### Step 8 — Build the detection application

Source: `app/camera-detect/detect_camera.py`
Deploy to: `/opt/camera-detect/detect_camera.py` on the EVK

**Architecture:**

```text
┌──────────────────────────────────────────────────────────────┐
│                    detect_camera.py                           │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌────────────────────────┐  │
│  │ v4l2src  │───→│ appsink  │───→│ Python processing      │  │
│  │ /video3  │    │ (RGB)    │    │  • ObjectDetector (SSD) │  │
│  │ 640x480  │    └──────────┘    │  • PoseEstimator (Move) │  │
│  └──────────┘                    │  • draw boxes+skeleton  │  │
│                                  │  • overlay FPS/latency  │  │
│  ┌──────────┐    ┌──────────┐    │  • M7 heartbeat        │  │
│  │ wayland  │←───│ appsrc   │←───│                        │  │
│  │ sink     │    │ (RGB)    │    └────────────────────────┘  │
│  │ HDMI J17 │    └──────────┘                                │
│  └──────────┘                                                │
└──────────────────────────────────────────────────────────────┘
```

**Modes:**

| Mode | Models | Best for |
| ---- | ------ | -------- |
| `--mode detect` | MobileNet SSD (objects) | Basic demo |
| `--mode pose` | MoveNet (17-joint skeleton) | Pose tracking |
| `--mode demo` | Both models simultaneously | **Demo video!** |
| `--mode demo --compare` | NPU + CPU for each model | Show NPU speedup |

**Key design choices:**

- **Two GStreamer pipelines**: capture (v4l2src→appsink) and display (appsrc→waylandsink), connected by Python processing loop
- **PIL for drawing** (not OpenCV — it's not in the image, and PIL is sufficient for boxes + skeleton)
- **Colored skeleton**: body regions use different colors (head=cyan, arms=green/yellow, legs=orange/red)
- **Corner accents**: bounding boxes have white corner markers for extra visual polish
- **M7 heartbeat**: optional, reads `/dev/ttyRPMSG0` in a background thread
- **`--compare` mode**: runs both NPU and CPU, shows speedup ratio on screen (e.g., "CPU: 45ms = 5x slower")

**Deploy and run:**

```bash
# Download models (on EVK with WiFi):
bash /opt/camera-detect/download_models.sh

# Or download on PC and transfer:
bash scripts/download_models.sh
scp /tmp/models/* root@192.168.1.98:/opt/models/

# Deploy app:
scp app/camera-detect/detect_camera.py root@192.168.1.98:/opt/camera-detect/

# Run on EVK (via SSH):
export XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1

python3 /opt/camera-detect/detect_camera.py --mode demo          # BEST for video
python3 /opt/camera-detect/detect_camera.py --mode demo --compare # show NPU vs CPU
python3 /opt/camera-detect/detect_camera.py --mode pose           # skeleton only
python3 /opt/camera-detect/detect_camera.py --cpu                 # CPU for comparison
```

**Dependencies** (all pre-installed in imx-image-multimedia):

| Package | Purpose |
| ------- | ------- |
| `tflite_runtime` | Inference engine with VX Delegate (NPU) |
| `Pillow` (PIL) | Drawing bounding boxes, skeleton, overlay text |
| `gi` (GStreamer Python) | Camera capture via V4L2, display via Wayland |
| `numpy` | Frame data manipulation |

**Models** (download with `scripts/download_models.sh`):

| Model | File | Size | Input | NPU Latency |
| ----- | ---- | ---- | ----- | ----------- |
| MobileNet SSD v1 INT8 | `detect.tflite` | 4.2 MB | 300×300 | ~9 ms |
| MoveNet Lightning INT8 | `movenet.tflite` | ~3 MB | 192×192 | ~10-15 ms |
| COCO labels | `labelmap.txt` | 1 KB | — | — |

### Step 9 — Add M7 FreeRTOS heartbeat via RPMsg

Source: `m7-firmware/rpmsg-heartbeat/main_remote.c`

**How it works:**

The i.MX8MP has a Cortex-M7 coprocessor alongside the A53 Linux cores. They communicate via RPMsg (Remote Processor Messaging) over shared memory:

```text
┌──────────────────┐    RPMsg (VirtIO)    ┌──────────────────┐
│  Cortex-A53 (×4) │◄══════════════════►│  Cortex-M7       │
│  Linux 6.6       │  /dev/ttyRPMSG0     │  FreeRTOS        │
│  detect_camera.py│  ←── "HB:42:5000"   │  heartbeat task  │
│                  │  ──→ "ping"          │  echo task       │
└──────────────────┘    MU interrupt      └──────────────────┘
        │                                          │
   ┌────┴────┐                              ┌──────┴──────┐
   │  DRAM   │  shared memory (64 KB)       │    TCM      │
   │  6 GB   │  @ 0x55800000               │  128 KB     │
   └─────────┘                              └─────────────┘
```

**The M7 firmware does:**

1. Sends `"HB:<counter>:<uptime_ms>"` every 1 second
2. Echoes back any message received from Linux with `"echo: "` prefix

**Build (on Ubuntu build host):**

```bash
# 1. Get NXP MCUXpresso SDK examples
git clone https://github.com/nxp-mcuxpresso/mcux-sdk-examples.git

# 2. Copy our modified main_remote.c over the NXP example
EXAMPLE=mcux-sdk-examples/boards/evkmimx8mp/multicore_examples/rpmsg_lite_str_echo_rtos
cp m7-firmware/rpmsg-heartbeat/main_remote.c ${EXAMPLE}/main_remote.c

# 3. Build with ARM GCC
cd ${EXAMPLE}/armgcc
export ARMGCC_DIR=/opt/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi
./build_release.sh
# Output: release/rpmsg_lite_str_echo_rtos.elf
```

**Load on the EVK:**

```bash
# Copy firmware to the board
scp release/rpmsg_lite_str_echo_rtos.elf root@192.168.1.98:/lib/firmware/rpmsg_heartbeat.elf

# On the EVK:
echo rpmsg_heartbeat.elf > /sys/class/remoteproc/remoteproc0/firmware
echo start > /sys/class/remoteproc/remoteproc0/state

# Verify
cat /sys/class/remoteproc/remoteproc0/state    # → "running"
ls /dev/ttyRPMSG*                               # → /dev/ttyRPMSG0
cat /dev/ttyRPMSG0 &                            # → HB:0:1000 HB:1:2000 ...
echo "ping" > /dev/ttyRPMSG0                    # → "echo: ping"
```

**Integration with detection app:**

The detection app automatically checks for `/dev/ttyRPMSG0` at startup. If the M7 firmware is running, it reads heartbeat messages in a background thread and displays `"M7: HB:42:5000"` on the HDMI overlay. If not running, it simply skips the M7 status display.

A helper script `m7-firmware/rpmsg-heartbeat/load_m7.sh` automates loading and testing.

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
| Object detection model | `/opt/models/detect.tflite` |
| Pose estimation model | `/opt/models/movenet.tflite` |
| COCO labels | `/opt/models/labelmap.txt` |
| Detection app | `/opt/camera-detect/detect_camera.py` |
| VX Delegate | `/usr/lib/libvx_delegate.so` |
| M7 firmware | `/lib/firmware/rpmsg_heartbeat.elf` |

**In the repo:**

| What | Path |
| ---- | ---- |
| This document | `docs/07-camera-npu.md` |
| Detection app source | `app/camera-detect/detect_camera.py` |
| Model download script | `scripts/download_models.sh` |
| Deploy script | `scripts/deploy_detect.sh` |
| M7 firmware source | `m7-firmware/rpmsg-heartbeat/main_remote.c` |
| M7 load/test script | `m7-firmware/rpmsg-heartbeat/load_m7.sh` |
| Demo video / GIF | `docs/assets/demo-detection.gif` |

## Troubleshooting

| Problem | Solution |
| ------- | -------- |
| OV5640 not detected | Re-seat mini-SAS cable on J12; check `dmesg` for I2C errors on bus 1 |
| No video on HDMI | `systemctl status weston.service`; re-seat HDMI cable on J17 |
| `waylandsink` fails (SSH) | `export XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1` |
| Model not found | Run `scripts/download_models.sh` on EVK or download on PC + scp |
| VX Delegate fails | `galcore` is built-in (not module); check `dmesg \| grep galcore` |
| MoveNet slow on NPU | Some ops may fall back to CPU; still faster than pure CPU |
| `/dev/ttyRPMSG*` missing | M7 firmware not loaded; see Step 9 load instructions |
| Low FPS in demo mode | Both models run sequentially; expected ~20 FPS in demo mode |
