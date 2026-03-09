#!/bin/bash
# Build imx-image-multimedia for i.MX8MP EVK
# Run this on the Ubuntu 22.04 build host
# Usage: bash build-multimedia.sh

set -e

BUILD_DIR="$HOME/imx-yocto-bsp/build-xwayland"
LOCAL_CONF="$BUILD_DIR/conf/local.conf"

echo "=== Step 1: Backup and update local.conf ==="

if [ ! -f "$LOCAL_CONF" ]; then
    echo "ERROR: $LOCAL_CONF not found. Is the build directory correct?"
    exit 1
fi

# Backup original
cp "$LOCAL_CONF" "$LOCAL_CONF.bak.$(date +%Y%m%d_%H%M%S)"
echo "Backed up local.conf"

# Remove any previous IMAGE_INSTALL:append lines we might have added
# (to avoid duplicates on re-run)
sed -i '/^# === M266 CUSTOM START ===/,/^# === M266 CUSTOM END ===/d' "$LOCAL_CONF"

# Append our custom configuration
cat >> "$LOCAL_CONF" << 'EOF'
# === M266 CUSTOM START ===

# Parallel build settings
BB_NUMBER_THREADS = "8"
PARALLEL_MAKE = "-j 8"

# Basic tools
IMAGE_INSTALL:append = " i2c-tools spidev-test devmem2 nano openssh-sftp-server python3 python3-pip"

# Camera + video (GStreamer, v4l2)
IMAGE_INSTALL:append = " v4l-utils gstreamer1.0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gst-examples"

# NPU / ML inference
IMAGE_INSTALL:append = " packagegroup-imx-ml"

# GStreamer Python bindings (for detection apps)
IMAGE_INSTALL:append = " python3-pygobject"

# Cairo mirror workaround (cairographics.org is slow/unreliable)
PREMIRRORS:prepend = "https://cairographics.org/.* https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/ \n"

# === M266 CUSTOM END ===
EOF

echo "Updated local.conf with multimedia packages"
echo ""

echo "=== Step 2: Enter build environment and start build ==="
cd "$HOME/imx-yocto-bsp"

# Use setup-environment (NOT imx-setup-release.sh) for existing build dir
if [ -f "setup-environment" ]; then
    echo "Using setup-environment..."
    EULA=1 MACHINE=imx8mpevk DISTRO=fsl-imx-xwayland source setup-environment build-xwayland
elif [ -f "sources/poky/oe-init-build-env" ]; then
    echo "Using oe-init-build-env fallback..."
    source sources/poky/oe-init-build-env build-xwayland
else
    echo "ERROR: Cannot find build environment setup script"
    exit 1
fi

echo ""
echo "Starting bitbake imx-image-multimedia..."
echo "This will take 1-3 hours (sstate-cache from imx-image-core will be reused)"
echo ""

bitbake imx-image-multimedia

echo ""
echo "=== Step 3: Build complete! ==="
echo ""

# Find the output image
DEPLOY_DIR="$BUILD_DIR/tmp/deploy/images/imx8mpevk"
WIC_FILE=$(ls -t "$DEPLOY_DIR"/imx-image-multimedia-imx8mpevk*.wic* 2>/dev/null | head -1)

if [ -n "$WIC_FILE" ]; then
    echo "Image file: $WIC_FILE"
    echo "File size: $(du -h "$WIC_FILE" | cut -f1)"
    echo ""
    echo "Next steps:"
    echo "  1. Copy this .wic file to your Windows machine"
    echo "  2. Use Rufus with DD image mode to flash to SD card"
    echo "  3. Set SW4 to: OFF OFF ON ON (SD boot)"
    echo "  4. Power on via J5 USB-C"
else
    echo "WARNING: Could not find .wic output file in $DEPLOY_DIR"
    echo "Check for errors above."
    ls -la "$DEPLOY_DIR"/ 2>/dev/null || echo "Deploy directory does not exist yet"
fi
