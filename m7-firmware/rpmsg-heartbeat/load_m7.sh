#!/bin/bash
# Load and test M7 RPMsg heartbeat firmware on i.MX8MP EVK
#
# Prerequisites:
#   - Built firmware ELF (rpmsg_heartbeat.elf) copied to /lib/firmware/
#   - Linux kernel with remoteproc + rpmsg support (default in imx-image-multimedia)
#
# Usage (on the EVK):
#   ./load_m7.sh              # Load and test
#   ./load_m7.sh stop         # Stop M7 firmware
#   ./load_m7.sh status       # Check status

FIRMWARE="rpmsg_heartbeat.elf"
REMOTEPROC="/sys/class/remoteproc/remoteproc0"
RPMSG_DEV="/dev/ttyRPMSG0"

case "${1:-start}" in
    start)
        echo "=== Loading M7 firmware: ${FIRMWARE} ==="

        # Check firmware exists
        if [ ! -f "/lib/firmware/${FIRMWARE}" ]; then
            echo "ERROR: /lib/firmware/${FIRMWARE} not found"
            echo "Copy the built ELF file first:"
            echo "  scp rpmsg_heartbeat.elf root@EVK_IP:/lib/firmware/"
            exit 1
        fi

        # Stop if already running
        STATE=$(cat ${REMOTEPROC}/state 2>/dev/null)
        if [ "$STATE" = "running" ]; then
            echo "M7 already running, stopping first..."
            echo stop > ${REMOTEPROC}/state
            sleep 1
        fi

        # Set firmware name and start
        echo ${FIRMWARE} > ${REMOTEPROC}/firmware
        echo start > ${REMOTEPROC}/state

        # Wait for RPMsg device to appear
        echo "Waiting for ${RPMSG_DEV}..."
        for i in $(seq 1 10); do
            if [ -e "${RPMSG_DEV}" ]; then
                echo "M7 is running! RPMsg device: ${RPMSG_DEV}"
                echo ""
                echo "=== Reading heartbeat (Ctrl+C to stop) ==="
                # Read a few heartbeat messages
                timeout 5 cat ${RPMSG_DEV} || true
                echo ""
                echo "=== Ping test ==="
                echo "ping" > ${RPMSG_DEV}
                sleep 1
                timeout 2 cat ${RPMSG_DEV} || true
                exit 0
            fi
            sleep 1
        done
        echo "ERROR: ${RPMSG_DEV} did not appear after 10s"
        echo "Check: dmesg | tail -30"
        exit 1
        ;;

    stop)
        echo "Stopping M7..."
        echo stop > ${REMOTEPROC}/state 2>/dev/null
        echo "State: $(cat ${REMOTEPROC}/state)"
        ;;

    status)
        echo "M7 state: $(cat ${REMOTEPROC}/state 2>/dev/null || echo 'unknown')"
        echo "Firmware: $(cat ${REMOTEPROC}/firmware 2>/dev/null || echo 'none')"
        ls -la ${RPMSG_DEV} 2>/dev/null && echo "RPMsg device exists" || echo "No RPMsg device"
        ;;

    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac
