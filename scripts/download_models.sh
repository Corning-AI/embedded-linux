#!/bin/bash
# Download TFLite models for the i.MX8MP detection demo
#
# Run ON THE EVK (requires internet via WiFi/Ethernet):
#   bash /opt/camera-detect/download_models.sh
#
# Or download on host PC and scp to the board:
#   bash scripts/download_models.sh
#   scp /tmp/models/* root@192.168.1.98:/opt/models/

set -e

# Detect if running on the EVK or host PC
if [ -d "/opt/models" ] || [ -f "/etc/imx-release" ]; then
    MODEL_DIR="/opt/models"
    echo "Running on EVK, saving to ${MODEL_DIR}"
else
    MODEL_DIR="/tmp/models"
    echo "Running on host PC, saving to ${MODEL_DIR}"
    echo "After download, transfer to EVK:"
    echo "  scp ${MODEL_DIR}/* root@192.168.1.98:/opt/models/"
fi

mkdir -p "${MODEL_DIR}"

# ── 1. MobileNet SSD v1 (Object Detection, INT8 quantized) ──────────────────
# 80 COCO classes: person, car, cup, phone, etc.
# Input: 300x300 uint8 RGB | Output: boxes, classes, scores
# NPU: ~9ms | CPU: ~45ms

DETECT="${MODEL_DIR}/detect.tflite"
LABELS="${MODEL_DIR}/labelmap.txt"

if [ -f "${DETECT}" ]; then
    echo "[1/2] detect.tflite already exists ($(du -h "${DETECT}" | cut -f1))"
else
    echo "[1/2] Downloading MobileNet SSD v1 COCO (INT8)..."
    TMPZIP="${MODEL_DIR}/ssd_model.zip"
    wget -q --show-progress -O "${TMPZIP}" \
        "https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip"
    cd "${MODEL_DIR}" && unzip -o "${TMPZIP}" detect.tflite labelmap.txt
    rm -f "${TMPZIP}"
    echo "  detect.tflite: $(du -h "${DETECT}" | cut -f1)"
fi

# ── 2. MoveNet SinglePose Lightning (Pose Estimation, INT8) ─────────────────
# 17-joint skeleton: nose, eyes, ears, shoulders, elbows, wrists, hips, knees, ankles
# Input: 192x192 uint8/int32 RGB | Output: [1,1,17,3] keypoints (y,x,conf)
# NPU: ~10-15ms | CPU: ~25-40ms

POSE="${MODEL_DIR}/movenet.tflite"

if [ -f "${POSE}" ]; then
    echo "[2/2] movenet.tflite already exists ($(du -h "${POSE}" | cut -f1))"
else
    echo "[2/2] Downloading MoveNet Lightning (INT8)..."
    wget -q --show-progress -O "${POSE}" \
        "https://storage.googleapis.com/tfhub-lite-models/google/lite-model/movenet/singlepose/lightning/tflite/int8/4.tflite"
    echo "  movenet.tflite: $(du -h "${POSE}" | cut -f1)"
fi

echo ""
echo "=== Models ready ==="
ls -lh "${MODEL_DIR}"/*.tflite "${MODEL_DIR}"/*.txt 2>/dev/null
echo ""
echo "To run the demo:"
echo "  export XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1"
echo "  python3 /opt/camera-detect/detect_camera.py --mode demo"
