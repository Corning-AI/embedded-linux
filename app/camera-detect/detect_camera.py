#!/usr/bin/env python3
"""
detect_camera.py — Real-time AI demo on i.MX8MP EVK

Pipeline:  OV5640 camera ──> NPU inference ──> visual overlay ──> HDMI display

Modes:
  detect  — Object detection (MobileNet SSD v1, 80 COCO classes)
  pose    — Pose estimation (MoveNet Lightning, 17-joint skeleton)
  demo    — Both models running simultaneously (most impressive!)

Hardware used:
  ISI   → camera DMA capture (/dev/video3)
  NPU   → ML inference via VX Delegate (~9ms object, ~15ms pose)
  GPU   → Weston compositing (waylandsink)
  M7    → FreeRTOS heartbeat via RPMsg (optional)
  WiFi  → deployment via SSH

Usage:
  export XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1

  python3 detect_camera.py                    # object detection (default)
  python3 detect_camera.py --mode pose        # skeleton drawing
  python3 detect_camera.py --mode demo        # both models = best for video!
  python3 detect_camera.py --mode demo --compare   # show NPU vs CPU latency
  python3 detect_camera.py --cpu              # CPU-only for comparison
  python3 detect_camera.py --no-display       # headless (console only)

Models (download with scripts/download_models.sh):
  /opt/models/detect.tflite    — MobileNet SSD v1 INT8 (4.2 MB)
  /opt/models/movenet.tflite   — MoveNet Lightning INT8 (3 MB)
  /opt/models/labelmap.txt     — COCO class names
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

CAMERA_DEV  = "/dev/video3"
WIDTH       = 640
HEIGHT      = 480
FPS         = 30
VX_DELEGATE = "/usr/lib/libvx_delegate.so"
RPMSG_DEV   = "/dev/ttyRPMSG0"

MODEL_DETECT = "/opt/models/detect.tflite"
MODEL_POSE   = "/opt/models/movenet.tflite"
LABEL_PATH   = "/opt/models/labelmap.txt"

# ── Colors ───────────────────────────────────────────────────────────────────

BOX_COLORS = [
    "#FF4444", "#44FF44", "#4444FF", "#FFFF44", "#FF44FF", "#44FFFF",
    "#FF8800", "#8800FF", "#00FF88", "#FF0088", "#88FF00", "#0088FF",
]

# Skeleton colors by body region
POSE_COLORS = {
    "head":  "#00FFFF",   # cyan
    "arm_l": "#00FF00",   # green
    "arm_r": "#FFFF00",   # yellow
    "torso": "#4488FF",   # blue
    "leg_l": "#FF8800",   # orange
    "leg_r": "#FF4444",   # red
}

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

# (start_idx, end_idx, region) — defines the skeleton lines
SKELETON = [
    (0, 1, "head"), (0, 2, "head"), (1, 3, "head"), (2, 4, "head"),
    (5, 6, "torso"),
    (5, 7, "arm_l"), (7, 9, "arm_l"),
    (6, 8, "arm_r"), (8, 10, "arm_r"),
    (5, 11, "torso"), (6, 12, "torso"), (11, 12, "torso"),
    (11, 13, "leg_l"), (13, 15, "leg_l"),
    (12, 14, "leg_r"), (14, 16, "leg_r"),
]


# ── Utility ──────────────────────────────────────────────────────────────────

def load_labels(path):
    """Load COCO label file. Line 0 is usually '???' (background)."""
    try:
        with open(path, "r") as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        print(f"Warning: {path} not found, using numeric class IDs")
        return [str(i) for i in range(91)]


def make_interpreter(model_path, use_npu=True):
    """Create a TFLite interpreter with optional NPU delegate."""
    delegates = []
    backend = "CPU"
    if use_npu:
        try:
            delegates = [tflite.load_delegate(VX_DELEGATE)]
            backend = "NPU"
        except (ValueError, OSError) as e:
            print(f"  NPU delegate failed ({e}), using CPU")
    interp = tflite.Interpreter(
        model_path=model_path,
        experimental_delegates=delegates,
        num_threads=4,
    )
    interp.allocate_tensors()
    return interp, backend


_font_cache = None

def get_font():
    """Load TrueType font (cached). Falls back to PIL default."""
    global _font_cache
    if _font_cache:
        return _font_cache
    for p in [
        "/usr/share/fonts/ttf/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/ttf/DejaVuSansMono-Bold.ttf",
    ]:
        try:
            _font_cache = (ImageFont.truetype(p, 18), ImageFont.truetype(p, 14))
            return _font_cache
        except (IOError, OSError):
            continue
    default = ImageFont.load_default()
    _font_cache = (default, default)
    return _font_cache


# ── Object Detector (MobileNet SSD) ─────────────────────────────────────────

class ObjectDetector:
    """MobileNet SSD v1 — detects 80 COCO object classes on NPU."""

    def __init__(self, model_path=MODEL_DETECT, use_npu=True):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"{model_path} not found. Run: scripts/download_models.sh"
            )
        self.interp, self.backend = make_interpreter(model_path, use_npu)

        inp = self.interp.get_input_details()[0]
        self.input_size = inp["shape"][1]
        self.input_idx = inp["index"]

        out = self.interp.get_output_details()
        self.out_idx = {
            "boxes":   out[0]["index"],
            "classes": out[1]["index"],
            "scores":  out[2]["index"],
            "count":   out[3]["index"],
        }

        # Warmup (first NPU inference compiles the graph)
        dummy = np.zeros((1, self.input_size, self.input_size, 3), dtype=np.uint8)
        self.interp.set_tensor(self.input_idx, dummy)
        self.interp.invoke()
        print(f"  ObjectDetector: {self.backend}, {self.input_size}x{self.input_size}")

    def detect(self, rgb_array, threshold=0.5):
        """Returns (detections, latency_ms). Each detection = (y0,x0,y1,x1,cls,score)."""
        resized = np.array(
            Image.fromarray(rgb_array).resize((self.input_size, self.input_size)),
            dtype=np.uint8,
        )
        self.interp.set_tensor(self.input_idx, np.expand_dims(resized, 0))

        t0 = time.monotonic()
        self.interp.invoke()
        ms = (time.monotonic() - t0) * 1000.0

        boxes   = self.interp.get_tensor(self.out_idx["boxes"])[0]
        classes = self.interp.get_tensor(self.out_idx["classes"])[0]
        scores  = self.interp.get_tensor(self.out_idx["scores"])[0]
        count   = int(self.interp.get_tensor(self.out_idx["count"])[0])

        results = []
        for i in range(min(count, len(scores))):
            if scores[i] >= threshold:
                ymin, xmin, ymax, xmax = boxes[i]
                results.append((ymin, xmin, ymax, xmax, int(classes[i]), float(scores[i])))
        return results, ms


# ── Pose Estimator (MoveNet) ────────────────────────────────────────────────

class PoseEstimator:
    """MoveNet SinglePose Lightning — 17-joint skeleton on NPU.

    Output: 17 keypoints, each (y, x, confidence) in normalized [0,1] coords.
    Draws colored skeleton lines connecting body joints.
    """

    def __init__(self, model_path=MODEL_POSE, use_npu=True):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"{model_path} not found. Run: scripts/download_models.sh"
            )
        self.interp, self.backend = make_interpreter(model_path, use_npu)

        inp = self.interp.get_input_details()[0]
        self.input_size = inp["shape"][1]  # 192 for Lightning
        self.input_idx = inp["index"]
        self.input_dtype = inp["dtype"]

        out = self.interp.get_output_details()[0]
        self.output_idx = out["index"]

        # Warmup
        dummy = np.zeros(inp["shape"], dtype=self.input_dtype)
        self.interp.set_tensor(self.input_idx, dummy)
        self.interp.invoke()
        print(f"  PoseEstimator: {self.backend}, {self.input_size}x{self.input_size}")

    def estimate(self, rgb_array):
        """Returns (keypoints, latency_ms). keypoints = [(y,x,conf)] × 17."""
        img = Image.fromarray(rgb_array).resize((self.input_size, self.input_size))
        input_data = np.expand_dims(np.array(img, dtype=self.input_dtype), 0)

        self.interp.set_tensor(self.input_idx, input_data)

        t0 = time.monotonic()
        self.interp.invoke()
        ms = (time.monotonic() - t0) * 1000.0

        # Output shape: [1, 1, 17, 3] → [17, 3]
        raw = self.interp.get_tensor(self.output_idx)
        kps = raw.reshape(17, 3)

        keypoints = [(float(kps[i][0]), float(kps[i][1]), float(kps[i][2]))
                     for i in range(17)]
        return keypoints, ms


# ── Drawing Functions ────────────────────────────────────────────────────────

def draw_boxes(draw, detections, labels, w, h):
    """Draw object detection bounding boxes."""
    font_big, font_small = get_font()

    for ymin, xmin, ymax, xmax, class_id, score in detections:
        x0, y0 = int(xmin * w), int(ymin * h)
        x1, y1 = int(xmax * w), int(ymax * h)
        color = BOX_COLORS[class_id % len(BOX_COLORS)]

        # Thick rectangle with corner accents
        draw.rectangle([x0, y0, x1, y1], outline=color, width=3)
        corner_len = min(20, (x1 - x0) // 4, (y1 - y0) // 4)
        for cx, cy, dx, dy in [
            (x0, y0, 1, 1), (x1, y0, -1, 1),
            (x0, y1, 1, -1), (x1, y1, -1, -1),
        ]:
            draw.line([(cx, cy), (cx + dx * corner_len, cy)], fill="white", width=2)
            draw.line([(cx, cy), (cx, cy + dy * corner_len)], fill="white", width=2)

        # Label
        if class_id < len(labels) and labels[class_id] not in ("???", ""):
            label = f"{labels[class_id]} {score:.0%}"
        else:
            label = f"class{class_id} {score:.0%}"

        bbox = draw.textbbox((x0, y0 - 20), label, font=font_small)
        draw.rectangle([bbox[0] - 1, bbox[1] - 1, bbox[2] + 1, bbox[3] + 1], fill=color)
        draw.text((x0, y0 - 20), label, fill="black", font=font_small)


def draw_skeleton(draw, keypoints, w, h, min_conf=0.3):
    """Draw pose estimation skeleton with colored body regions."""
    def kp_px(idx):
        y, x, c = keypoints[idx]
        return int(x * w), int(y * h), c

    # Draw lines first (behind dots)
    for i, j, region in SKELETON:
        px_i, py_i, ci = kp_px(i)
        px_j, py_j, cj = kp_px(j)
        if ci > min_conf and cj > min_conf:
            color = POSE_COLORS.get(region, "#FFFFFF")
            draw.line([(px_i, py_i), (px_j, py_j)], fill=color, width=4)

    # Draw keypoint dots
    for idx in range(17):
        px, py, conf = kp_px(idx)
        if conf > min_conf:
            r = 6 if idx == 0 else 5  # nose slightly larger
            draw.ellipse([px - r, py - r, px + r, py + r],
                         fill="#FFFFFF", outline="#000000", width=1)


def draw_overlay(draw, info_lines, w, h):
    """Draw semi-transparent info overlay at top-left."""
    font_big, _ = get_font()
    y = 6
    for line in info_lines:
        bbox = draw.textbbox((10, y), line, font=font_big)
        draw.rectangle(
            [bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2],
            fill=(0, 0, 0, 200),
        )
        draw.text((10, y), line, fill="#00FF00", font=font_big)
        y = bbox[3] + 4


# ── RPMsg M7 Heartbeat (Optional) ───────────────────────────────────────────

class M7HeartbeatReader:
    """Read heartbeat from Cortex-M7 via /dev/ttyRPMSG0 (background thread)."""

    def __init__(self, device=RPMSG_DEV):
        self.status = ""
        self.device = device
        self._running = False

    def start(self):
        if not os.path.exists(self.device):
            return
        self._running = True
        threading.Thread(target=self._reader, daemon=True).start()
        print(f"  M7 RPMsg: {self.device}")

    def stop(self):
        self._running = False

    def _reader(self):
        try:
            with open(self.device, "r") as f:
                while self._running:
                    line = f.readline().strip()
                    if line:
                        self.status = line
        except Exception as e:
            self.status = f"err:{e}"


# ── GStreamer Helpers ────────────────────────────────────────────────────────

def sample_to_numpy(sample, width, height):
    buf = sample.get_buffer()
    ok, info = buf.map(Gst.MapFlags.READ)
    if not ok:
        return None
    try:
        return np.frombuffer(info.data, dtype=np.uint8).reshape(height, width, 3).copy()
    finally:
        buf.unmap(info)


def numpy_to_buffer(array):
    data = array.tobytes()
    buf = Gst.Buffer.new_allocate(None, len(data), None)
    buf.fill(0, data)
    return buf


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="i.MX8MP real-time AI demo (camera + NPU + HDMI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  %(prog)s --mode demo          # objects + skeleton (best for video!)\n"
               "  %(prog)s --mode pose           # skeleton only\n"
               "  %(prog)s --mode demo --compare # show NPU vs CPU latency\n",
    )
    parser.add_argument("--mode", choices=["detect", "pose", "demo"], default="detect",
                        help="detect=objects, pose=skeleton, demo=both (default: detect)")
    parser.add_argument("--cpu", action="store_true", help="CPU-only (for comparison)")
    parser.add_argument("--compare", action="store_true",
                        help="Run BOTH NPU and CPU, show latency comparison on screen")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Detection confidence threshold")
    parser.add_argument("--device", default=CAMERA_DEV, help="V4L2 camera device")
    parser.add_argument("--no-display", action="store_true", help="Headless mode")
    args = parser.parse_args()

    # ── Wayland env (for SSH sessions) ──
    if not args.no_display:
        os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/0")
        os.environ.setdefault("WAYLAND_DISPLAY", "wayland-1")

    Gst.init(None)
    print("Loading models...")

    # ── Initialize models based on mode ──
    use_npu = not args.cpu
    detector = None
    pose = None
    detector_cpu = None   # for --compare mode
    pose_cpu = None

    if args.mode in ("detect", "demo"):
        detector = ObjectDetector(MODEL_DETECT, use_npu=use_npu)
        if args.compare and use_npu:
            detector_cpu = ObjectDetector(MODEL_DETECT, use_npu=False)

    if args.mode in ("pose", "demo"):
        pose = PoseEstimator(MODEL_POSE, use_npu=use_npu)
        if args.compare and use_npu:
            pose_cpu = PoseEstimator(MODEL_POSE, use_npu=False)

    labels = load_labels(LABEL_PATH)

    # ── M7 heartbeat ──
    m7 = M7HeartbeatReader()
    m7.start()

    # ── GStreamer capture pipeline ──
    cap_pipe = Gst.parse_launch(
        f"v4l2src device={args.device} ! "
        f"video/x-raw,width={WIDTH},height={HEIGHT},framerate={FPS}/1 ! "
        f"videoconvert ! video/x-raw,format=RGB ! "
        f"appsink name=sink emit-signals=false max-buffers=2 drop=true"
    )
    appsink = cap_pipe.get_by_name("sink")

    # ── GStreamer display pipeline ──
    disp_pipe = None
    appsrc = None
    if not args.no_display:
        disp_pipe = Gst.parse_launch(
            f"appsrc name=src is-live=true format=time "
            f"caps=video/x-raw,format=RGB,width={WIDTH},height={HEIGHT},"
            f"framerate={FPS}/1 ! "
            f"videoconvert ! waylandsink sync=false"
        )
        appsrc = disp_pipe.get_by_name("src")

    # ── Start ──
    cap_pipe.set_state(Gst.State.PLAYING)
    if disp_pipe:
        disp_pipe.set_state(Gst.State.PLAYING)

    mode_desc = {"detect": "Object Detection", "pose": "Pose Estimation",
                 "demo": "Full Demo (Objects + Pose)"}
    print(f"\n{'='*50}")
    print(f"  Mode: {mode_desc[args.mode]}")
    print(f"  Camera: {args.device}")
    print(f"  Backend: {'CPU' if args.cpu else 'NPU'}"
          f"{'  +compare' if args.compare else ''}")
    print(f"{'='*50}")
    print("Press Ctrl+C to stop\n")

    # ── Main loop ──
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
            sample = appsink.emit("pull-sample")
            if sample is None:
                time.sleep(0.01)
                continue

            frame = sample_to_numpy(sample, WIDTH, HEIGHT)
            if frame is None:
                continue

            # ── Run inference ──
            detections = []
            keypoints = None
            det_ms = 0.0
            pose_ms = 0.0
            det_cpu_ms = 0.0
            pose_cpu_ms = 0.0

            if detector:
                detections, det_ms = detector.detect(frame, args.threshold)
            if pose:
                keypoints, pose_ms = pose.estimate(frame)

            # Compare mode: also run on CPU
            if detector_cpu:
                _, det_cpu_ms = detector_cpu.detect(frame, args.threshold)
            if pose_cpu:
                _, pose_cpu_ms = pose_cpu.estimate(frame)

            total_ms = det_ms + pose_ms

            # ── FPS ──
            frame_count += 1
            now = time.monotonic()
            if now - fps_time >= 1.0:
                fps = frame_count / (now - fps_time)
                frame_count = 0
                fps_time = now

            # ── Console output ──
            if args.no_display:
                parts = []
                if detections:
                    for y0, x0, y1, x1, cls, sc in detections:
                        name = labels[cls] if cls < len(labels) else f"#{cls}"
                        parts.append(f"{name}:{sc:.0%}")
                if keypoints:
                    visible = sum(1 for _, _, c in keypoints if c > 0.3)
                    parts.append(f"pose:{visible}/17")
                if parts:
                    print(f"  {' | '.join(parts)}  [{total_ms:.1f}ms {fps:.1f}FPS]")
                continue

            # ── Draw on frame ──
            pil_img = Image.fromarray(frame)
            draw = ImageDraw.Draw(pil_img)

            if keypoints:
                draw_skeleton(draw, keypoints, WIDTH, HEIGHT)
            if detections:
                draw_boxes(draw, detections, labels, WIDTH, HEIGHT)

            # ── Info overlay ──
            info = []
            if detector:
                line = f"Detect: {detector.backend} {det_ms:.1f}ms"
                if args.compare and det_cpu_ms > 0:
                    speedup = det_cpu_ms / det_ms if det_ms > 0 else 0
                    line += f"  (CPU: {det_cpu_ms:.1f}ms = {speedup:.1f}x slower)"
                info.append(line)
            if pose:
                line = f"Pose:   {pose.backend} {pose_ms:.1f}ms"
                if args.compare and pose_cpu_ms > 0:
                    speedup = pose_cpu_ms / pose_ms if pose_ms > 0 else 0
                    line += f"  (CPU: {pose_cpu_ms:.1f}ms = {speedup:.1f}x slower)"
                info.append(line)

            obj_count = len(detections)
            kp_count = sum(1 for _, _, c in keypoints if c > 0.3) if keypoints else 0
            summary = f"{fps:.0f} FPS | {obj_count} obj"
            if keypoints:
                summary += f" | {kp_count}/17 joints"
            info.append(summary)

            if m7.status:
                info.append(f"M7: {m7.status}")

            draw_overlay(draw, info, WIDTH, HEIGHT)

            # ── Push to display ──
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
