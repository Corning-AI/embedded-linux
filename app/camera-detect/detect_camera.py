#!/usr/bin/env python3
"""
detect_camera.py — Real-time object detection on i.MX8MP EVK

Pipeline:  OV5640 camera ──> NPU inference ──> bounding boxes ──> HDMI display

Hardware:
  - Camera:  OV5640 on /dev/video3 (ISI capture, NOT video0!)
  - NPU:     Vivante GC7000UL via VX Delegate (~9ms per frame)
  - Display: Weston/Wayland on HDMI (J17)

Usage:
  # Run from SSH (must set Wayland env vars):
  export XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1

  python3 detect_camera.py              # NPU mode (default)
  python3 detect_camera.py --cpu        # CPU mode (~45ms, for comparison)
  python3 detect_camera.py --threshold 0.3   # Lower confidence
  python3 detect_camera.py --no-display      # Headless (console output only)

Requirements (all pre-installed in imx-image-multimedia):
  - tflite_runtime 2.16+
  - Pillow (PIL)
  - gi (GStreamer 1.0 Python bindings)
"""

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import tflite_runtime.interpreter as tflite
import argparse
import os
import signal
import sys
import time
import threading

# ── Configuration ────────────────────────────────────────────────────────────

CAMERA_DEV   = "/dev/video3"     # ISI capture (video0=VPU enc, video1=VPU dec)
WIDTH        = 640
HEIGHT       = 480
FPS          = 30
MODEL_PATH   = "/opt/models/detect.tflite"
LABEL_PATH   = "/opt/models/labelmap.txt"
VX_DELEGATE  = "/usr/lib/libvx_delegate.so"
RPMSG_DEV    = "/dev/ttyRPMSG0"  # M7 heartbeat (optional, Step 9)

# Colors for bounding boxes (one per class, cycling)
BOX_COLORS = [
    "#FF4444", "#44FF44", "#4444FF", "#FFFF44", "#FF44FF", "#44FFFF",
    "#FF8800", "#8800FF", "#00FF88", "#FF0088", "#88FF00", "#0088FF",
]


# ── Label Loading ────────────────────────────────────────────────────────────

def load_labels(path):
    """Load COCO label file. Line 0 is usually '???' (background)."""
    try:
        with open(path, "r") as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        print(f"Warning: {path} not found, using numeric class IDs")
        return [str(i) for i in range(91)]


# ── TFLite Detector ──────────────────────────────────────────────────────────

class Detector:
    """MobileNet SSD v1 detector with optional NPU acceleration."""

    def __init__(self, model_path, use_npu=True):
        delegates = []
        self.backend = "CPU"

        if use_npu:
            try:
                delegates = [tflite.load_delegate(VX_DELEGATE)]
                self.backend = "NPU"
            except (ValueError, OSError) as e:
                print(f"Warning: NPU delegate failed ({e}), falling back to CPU")

        self.interpreter = tflite.Interpreter(
            model_path=model_path,
            experimental_delegates=delegates,
            num_threads=4,
        )
        self.interpreter.allocate_tensors()

        inp = self.interpreter.get_input_details()[0]
        self.input_size = inp["shape"][1]  # 300 for MobileNet SSD
        self.input_idx = inp["index"]

        out = self.interpreter.get_output_details()
        # MobileNet SSD v1 output order: boxes, classes, scores, count
        self.out_idx = {
            "boxes":   out[0]["index"],   # [1, N, 4] normalized ymin,xmin,ymax,xmax
            "classes": out[1]["index"],   # [1, N] class IDs (float)
            "scores":  out[2]["index"],   # [1, N] confidence scores
            "count":   out[3]["index"],   # [1] number of detections
        }

        # Warmup — first inference compiles the NPU graph, takes longer
        dummy = np.zeros((1, self.input_size, self.input_size, 3), dtype=np.uint8)
        self.interpreter.set_tensor(self.input_idx, dummy)
        self.interpreter.invoke()
        print(f"Detector ready: {self.backend}, input={self.input_size}x{self.input_size}")

    def detect(self, rgb_array, threshold=0.5):
        """
        Run detection on an RGB numpy array (H, W, 3) uint8.
        Returns: (detections, latency_ms)
          detections = list of (ymin, xmin, ymax, xmax, class_id, score)
          coordinates are normalized [0, 1]
        """
        img = Image.fromarray(rgb_array)
        resized = img.resize((self.input_size, self.input_size))
        input_data = np.expand_dims(np.array(resized, dtype=np.uint8), axis=0)

        self.interpreter.set_tensor(self.input_idx, input_data)

        t0 = time.monotonic()
        self.interpreter.invoke()
        latency_ms = (time.monotonic() - t0) * 1000.0

        boxes   = self.interpreter.get_tensor(self.out_idx["boxes"])[0]
        classes = self.interpreter.get_tensor(self.out_idx["classes"])[0]
        scores  = self.interpreter.get_tensor(self.out_idx["scores"])[0]
        count   = int(self.interpreter.get_tensor(self.out_idx["count"])[0])

        results = []
        for i in range(min(count, len(scores))):
            if scores[i] >= threshold:
                ymin, xmin, ymax, xmax = boxes[i]
                results.append((ymin, xmin, ymax, xmax, int(classes[i]), float(scores[i])))

        return results, latency_ms


# ── Drawing ──────────────────────────────────────────────────────────────────

def get_font():
    """Try to load a TrueType font, fall back to PIL default."""
    font_paths = [
        "/usr/share/fonts/ttf/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/ttf/DejaVuSansMono-Bold.ttf",
    ]
    for p in font_paths:
        try:
            return ImageFont.truetype(p, 16), ImageFont.truetype(p, 14)
        except (IOError, OSError):
            continue
    default = ImageFont.load_default()
    return default, default


def draw_detections(image, detections, labels, latency_ms, fps, backend, m7_status=""):
    """Draw bounding boxes and info overlay on a PIL Image (modifies in place)."""
    draw = ImageDraw.Draw(image)
    w, h = image.size
    font_big, font_small = get_font()

    # ── Bounding boxes ──
    for ymin, xmin, ymax, xmax, class_id, score in detections:
        x0, y0 = int(xmin * w), int(ymin * h)
        x1, y1 = int(xmax * w), int(ymax * h)
        color = BOX_COLORS[class_id % len(BOX_COLORS)]

        # Rectangle
        draw.rectangle([x0, y0, x1, y1], outline=color, width=3)

        # Label text
        if class_id < len(labels) and labels[class_id] not in ("???", ""):
            label = f"{labels[class_id]} {score:.0%}"
        else:
            label = f"class{class_id} {score:.0%}"

        # Label background
        bbox = draw.textbbox((x0, y0 - 18), label, font=font_small)
        draw.rectangle(
            [bbox[0] - 1, bbox[1] - 1, bbox[2] + 1, bbox[3] + 1],
            fill=color,
        )
        draw.text((x0, y0 - 18), label, fill="black", font=font_small)

    # ── Info overlay (top-left) ──
    lines = [f"{backend} | {latency_ms:.1f}ms | {fps:.1f} FPS | {len(detections)} obj"]
    if m7_status:
        lines.append(f"M7: {m7_status}")

    y_offset = 4
    for line in lines:
        bbox = draw.textbbox((8, y_offset), line, font=font_big)
        draw.rectangle(
            [bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2],
            fill=(0, 0, 0, 180),
        )
        draw.text((8, y_offset), line, fill="#00FF00", font=font_big)
        y_offset = bbox[3] + 4

    return image


# ── RPMsg M7 Heartbeat Reader (Optional, Step 9) ────────────────────────────

class M7HeartbeatReader:
    """Read heartbeat messages from Cortex-M7 via RPMsg (non-blocking)."""

    def __init__(self, device=RPMSG_DEV):
        self.status = ""
        self.device = device
        self._thread = None
        self._running = False

    def start(self):
        if not os.path.exists(self.device):
            print(f"M7 RPMsg: {self.device} not found (M7 firmware not loaded?)")
            return
        self._running = True
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        print(f"M7 RPMsg: reading from {self.device}")

    def stop(self):
        self._running = False

    def _reader(self):
        """Background thread: read lines from /dev/ttyRPMSG0."""
        try:
            with open(self.device, "r") as f:
                while self._running:
                    line = f.readline().strip()
                    if line:
                        self.status = line
        except Exception as e:
            self.status = f"error: {e}"


# ── GStreamer Helpers ────────────────────────────────────────────────────────

def sample_to_numpy(sample, width, height):
    """Convert GstSample → numpy RGB array (H, W, 3)."""
    buf = sample.get_buffer()
    ok, info = buf.map(Gst.MapFlags.READ)
    if not ok:
        return None
    try:
        return np.frombuffer(info.data, dtype=np.uint8).reshape(height, width, 3).copy()
    finally:
        buf.unmap(info)


def numpy_to_buffer(array):
    """Convert numpy RGB array → GstBuffer."""
    data = array.tobytes()
    buf = Gst.Buffer.new_allocate(None, len(data), None)
    buf.fill(0, data)
    return buf


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="i.MX8MP real-time object detection (camera + NPU + HDMI)"
    )
    parser.add_argument("--cpu", action="store_true", help="CPU-only inference")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Detection confidence threshold (0.0-1.0)")
    parser.add_argument("--device", default=CAMERA_DEV,
                        help="V4L2 camera device path")
    parser.add_argument("--no-display", action="store_true",
                        help="Headless mode (print to console)")
    args = parser.parse_args()

    # ── Wayland environment (needed when running via SSH) ──
    if not args.no_display:
        os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/0")
        os.environ.setdefault("WAYLAND_DISPLAY", "wayland-1")

    Gst.init(None)

    # ── Load model and labels ──
    print(f"Model: {MODEL_PATH}")
    detector = Detector(MODEL_PATH, use_npu=not args.cpu)
    labels = load_labels(LABEL_PATH)

    # ── M7 heartbeat (optional) ──
    m7 = M7HeartbeatReader()
    m7.start()

    # ── Capture pipeline: camera → RGB frames ──
    cap_str = (
        f"v4l2src device={args.device} ! "
        f"video/x-raw,width={WIDTH},height={HEIGHT},framerate={FPS}/1 ! "
        f"videoconvert ! video/x-raw,format=RGB ! "
        f"appsink name=sink emit-signals=false max-buffers=2 drop=true"
    )
    cap_pipe = Gst.parse_launch(cap_str)
    appsink = cap_pipe.get_by_name("sink")

    # ── Display pipeline: annotated frames → HDMI ──
    disp_pipe = None
    appsrc = None
    if not args.no_display:
        disp_str = (
            f"appsrc name=src is-live=true format=time "
            f"caps=video/x-raw,format=RGB,width={WIDTH},height={HEIGHT},"
            f"framerate={FPS}/1 ! "
            f"videoconvert ! waylandsink sync=false"
        )
        disp_pipe = Gst.parse_launch(disp_str)
        appsrc = disp_pipe.get_by_name("src")

    # ── Start ──
    cap_pipe.set_state(Gst.State.PLAYING)
    if disp_pipe:
        disp_pipe.set_state(Gst.State.PLAYING)

    print(f"Running: camera={args.device} | {detector.backend} | "
          f"threshold={args.threshold}")
    print("Press Ctrl+C to stop\n")

    # ── Main processing loop ──
    running = True
    frame_count = 0
    fps = 0.0
    fps_time = time.monotonic()

    def on_sigint(sig, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, on_sigint)

    try:
        while running:
            # Pull frame (blocking)
            sample = appsink.emit("pull-sample")
            if sample is None:
                time.sleep(0.01)
                continue

            frame = sample_to_numpy(sample, WIDTH, HEIGHT)
            if frame is None:
                continue

            # ── Inference ──
            detections, latency_ms = detector.detect(frame, args.threshold)

            # ── FPS counter ──
            frame_count += 1
            now = time.monotonic()
            elapsed = now - fps_time
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                fps_time = now

            # ── Output ──
            if args.no_display:
                # Console mode
                for ymin, xmin, ymax, xmax, cls, score in detections:
                    name = labels[cls] if cls < len(labels) else f"#{cls}"
                    print(f"  {name}: {score:.0%} "
                          f"({xmin:.2f},{ymin:.2f})-({xmax:.2f},{ymax:.2f})")
                if detections:
                    print(f"  [{detector.backend} {latency_ms:.1f}ms | "
                          f"{fps:.1f} FPS]\n")
            else:
                # Draw boxes and push to display
                pil_img = Image.fromarray(frame)
                draw_detections(
                    pil_img, detections, labels,
                    latency_ms, fps, detector.backend,
                    m7_status=m7.status,
                )
                buf = numpy_to_buffer(np.array(pil_img))
                buf.pts = Gst.CLOCK_TIME_NONE
                appsrc.emit("push-buffer", buf)

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        raise
    finally:
        print("\nShutting down...")
        m7.stop()
        cap_pipe.set_state(Gst.State.NULL)
        if disp_pipe:
            disp_pipe.set_state(Gst.State.NULL)


if __name__ == "__main__":
    main()
