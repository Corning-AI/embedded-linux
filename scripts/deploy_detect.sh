#!/bin/bash
# Deploy the detection app to the i.MX8MP EVK via SSH
#
# Usage:
#   ./scripts/deploy_detect.sh [EVK_IP]
#   ./scripts/deploy_detect.sh 192.168.1.98
#
# What it does:
#   1. Copies detect_camera.py to /opt/camera-detect/ on the board
#   2. Creates a systemd service for auto-start (optional)
#   3. Runs a quick sanity check

EVK_IP="${1:-192.168.1.98}"
EVK_USER="root"
REMOTE_DIR="/opt/camera-detect"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_SRC="$SCRIPT_DIR/app/camera-detect/detect_camera.py"

echo "=== Deploy detection app to i.MX8MP EVK ==="
echo "Target: ${EVK_USER}@${EVK_IP}:${REMOTE_DIR}"
echo ""

# Check source exists
if [ ! -f "$APP_SRC" ]; then
    echo "ERROR: $APP_SRC not found"
    exit 1
fi

# Create remote directory and copy
ssh ${EVK_USER}@${EVK_IP} "mkdir -p ${REMOTE_DIR}"
scp "$APP_SRC" ${EVK_USER}@${EVK_IP}:${REMOTE_DIR}/detect_camera.py
ssh ${EVK_USER}@${EVK_IP} "chmod +x ${REMOTE_DIR}/detect_camera.py"

echo ""
echo "=== Verify deployment ==="
ssh ${EVK_USER}@${EVK_IP} "ls -la ${REMOTE_DIR}/ && echo '' && python3 -c 'import tflite_runtime; print(\"tflite_runtime:\", tflite_runtime.__version__)'"

echo ""
echo "=== Done! ==="
echo "To run on the board:"
echo "  ssh ${EVK_USER}@${EVK_IP}"
echo "  export XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1"
echo "  python3 ${REMOTE_DIR}/detect_camera.py"
echo ""
echo "Or headless (no HDMI):"
echo "  python3 ${REMOTE_DIR}/detect_camera.py --no-display"
