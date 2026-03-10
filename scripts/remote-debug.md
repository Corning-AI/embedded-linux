# Remote Debugging Guide for Claude Code

How to control the i.MX8MP EVK board wirelessly from this Windows PC via SSH.
Any Claude Code session can follow this guide to execute commands on the board.

## Quick Start

```bash
# Test connectivity (should reply in <500ms)
ping -n 1 -w 3000 192.168.1.98

# Run any command on the board
ssh -o ConnectTimeout=5 root@192.168.1.98 "your_command_here"

# Transfer file TO the board
scp local_file root@192.168.1.98:/remote/path/

# Transfer file FROM the board
scp root@192.168.1.98:/remote/path/file ./local_path/
```

## Connection Details

| Item | Value |
|------|-------|
| Board IP | `192.168.1.98` |
| User | `root` (no password) |
| SSH port | 22 (default) |
| Hostname | `imx8mpevk` |
| WiFi interface | `mlan0` (NXP 88W8997 PCIe) |
| Kernel | `6.6.52-lts` |

## Common Operations

### Run a command and get output

```bash
ssh -o ConnectTimeout=5 root@192.168.1.98 "i2cdetect -y 2"
```

Always use `-o ConnectTimeout=5` to avoid hanging if the board is offline.

### Run a long command (with timeout)

```bash
# Use Bash tool with timeout=30000 or higher
ssh -o ConnectTimeout=5 root@192.168.1.98 "python3 -u /opt/camera-detect/detect_camera.py --mode detect --no-display 2>&1 | head -20"
```

### Transfer a file to the board

```bash
scp -o ConnectTimeout=10 "C:\path\to\local\file" root@192.168.1.98:/opt/destination/
```

### Transfer a file from the board

```bash
scp -o ConnectTimeout=10 root@192.168.1.98:/remote/file "C:\local\path\"
```

### Run Python script on the board

```bash
# Inline Python (short scripts)
ssh root@192.168.1.98 "python3 -c \"print('hello from EVK')\""

# Multi-line Python (use heredoc-style via ssh)
ssh root@192.168.1.98 "python3 -u -c '
import os
print(os.uname())
print(os.listdir(\"/opt/models/\"))
'"
```

### Deploy a Python file and run it

```bash
scp my_script.py root@192.168.1.98:/tmp/ && ssh root@192.168.1.98 "python3 -u /tmp/my_script.py"
```

## I2C Sensor Operations

```bash
# List all I2C buses
ssh root@192.168.1.98 "i2cdetect -l"

# Scan I2C3 (expansion header J21 pins 3+5, bus number = 2 in Linux)
ssh root@192.168.1.98 "i2cdetect -y 2"

# Read a register (example: BME280 chip ID at 0xD0)
ssh root@192.168.1.98 "i2cget -y 2 0x76 0xd0"

# Write a register
ssh root@192.168.1.98 "i2cset -y 2 0x76 0xf2 0x01"
```

### J21 Expansion Header Pinout (for sensor wiring)

| J21 Pin | Function | I2C Bus |
|---------|----------|---------|
| Pin 1 | 3.3V power | — |
| Pin 6 | GND | — |
| Pin 3 | I2C3_SDA | i2c-2 (A53 Linux) |
| Pin 5 | I2C3_SCL | i2c-2 (A53 Linux) |
| Pin 27 | I2C2_SDA | i2c-1 |
| Pin 28 | I2C2_SCL | i2c-1 |

## Kernel Module Operations

```bash
# Copy module to board
scp kernel-modules/bme280/bme280_i2c.ko root@192.168.1.98:/tmp/

# Load
ssh root@192.168.1.98 "insmod /tmp/bme280_i2c.ko"

# Check kernel log
ssh root@192.168.1.98 "dmesg | tail -10"

# Unload
ssh root@192.168.1.98 "rmmod bme280_i2c"
```

## Display / Weston Operations

```bash
# Restart Weston (if display is frozen or to reload wallpaper)
ssh root@192.168.1.98 "systemctl restart weston.service"

# Run a GUI app on HDMI (must set Wayland env vars)
ssh root@192.168.1.98 "XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1 your_gui_app"

# Camera preview on HDMI
ssh root@192.168.1.98 "XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1 gst-launch-1.0 v4l2src device=/dev/video3 ! video/x-raw,width=640,height=480 ! waylandsink &"

# Deploy a new wallpaper
scp wallpaper.png root@192.168.1.98:/usr/share/weston/evk_wallpaper.png
ssh root@192.168.1.98 "systemctl restart weston.service"
```

## System Monitoring

```bash
# CPU temperature (divide by 1000 for °C)
ssh root@192.168.1.98 "cat /sys/class/thermal/thermal_zone0/temp"

# Memory
ssh root@192.168.1.98 "free -h"

# Disk
ssh root@192.168.1.98 "df -h /"

# WiFi signal
ssh root@192.168.1.98 "iw dev mlan0 link"

# Running processes
ssh root@192.168.1.98 "ps aux | head -20"
```

## Weston Configuration

Config file: `/etc/xdg/weston/weston.ini`

Current settings:
- `panel-position=none` (taskbar hidden)
- `background-image=/usr/share/weston/evk_wallpaper.png`
- `background-type=scale`
- `idle-time=0` (no screen timeout)

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ping` fails | Board not powered on, or WiFi not connected. Check power (J5 USB-C, SW3 ON) |
| `ssh` hangs | Use `-o ConnectTimeout=5` to fail fast. Board IP may have changed |
| `Connection refused` | SSHD not running: `systemctl start sshd` via serial console |
| WiFi disconnected | `ssh root@... "systemctl restart wifi-connect.service"` |
| Weston crashed | `ssh root@... "systemctl restart weston.service"` |
| Serial fallback | COM5 at 115200 baud (J23 micro-USB, 3rd port = A53) |

## Important Notes

- Always use `python3 -u` when running Python via SSH (unbuffered stdout)
- The board has no password for root — SSH just works
- WiFi auto-starts on boot via `wifi-connect.service`
- `/dev/video3` is the camera (ISI capture), NOT video0
- NPU delegate: `/usr/lib/libvx_delegate.so`
- Models stored at: `/opt/models/`
- Detection app: `/opt/camera-detect/detect_camera.py`
