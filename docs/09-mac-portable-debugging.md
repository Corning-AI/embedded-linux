# 09 — Mac Portable Debugging Guide

A complete guide for debugging the i.MX 8M Plus EVK from a Mac laptop using only a power bank — no monitor, no keyboard, no Ethernet cable. Everything goes through Wi-Fi SSH.

## What to Bring

| Item | Requirement | Notes |
|------|-------------|-------|
| Mac laptop | Any recent MacBook (Intel or Apple Silicon) | Terminal + SSH built-in |
| Anker power bank | **≥ 45 W USB-C PD output** | Models: 525 (45W), 737 (140W), 747 (87W), Prime (250W) |
| USB-C cable | PD-capable, ≥ 60 W rated | Comes with the EVK or the power bank |
| i.MX 8M Plus EVK | SD card inserted, SW4 = `OFF OFF ON ON` | Pre-configured image with Wi-Fi auto-start |
| (Optional) USB micro-B cable | For debug UART via J23 | Only needed if Wi-Fi fails |
| (Optional) HDMI cable | For camera/GUI output | Only needed if you want to see the display |

### Power Bank Selection Guide

The EVK requires **USB-C Power Delivery at 45 W** through connector **J5** (Port0). Not all power banks support this.

| Anker Model | Capacity | PD Output | Can Power EVK? | Runtime Estimate |
|-------------|----------|-----------|----------------|-----------------|
| Nano 10K | 10000 mAh | 30 W | **No** — insufficient | — |
| 525 | 20000 mAh | 45 W | **Yes** — minimum viable | ~4 hours |
| 737 PowerCore 24K | 24000 mAh | 140 W | **Yes** — recommended | ~5–6 hours |
| 747 PowerCore 26K | 25600 mAh | 87 W | **Yes** — great choice | ~5–6 hours |
| Prime 27650 | 27650 mAh | 250 W | **Yes** — overkill but works | ~6+ hours |

> **Rule of thumb:** If the power bank can charge a MacBook Pro, it can power the EVK.

Runtime estimate assumes ~10–15 W average EVK consumption (idle + Wi-Fi + occasional NPU inference).

## Network Architecture

### The NTU Problem

NTU campus Wi-Fi (NTUSECURE / eduroam) uses **802.1X enterprise authentication** with these challenges:

| Issue | Impact |
|-------|--------|
| 802.1X (EAP-PEAP) | Requires `wpa_supplicant` with EAP config — complex on embedded Linux |
| **Client isolation** | Devices on the same SSID **cannot see each other** — SSH will fail |
| Captive portal | Some networks require browser login — EVK has no browser |
| MAC registration | Some networks require whitelisting the device MAC address |

**Client isolation is the showstopper.** Even if both Mac and EVK join NTU Wi-Fi, the network blocks device-to-device traffic.

### Solution: Mac Personal Hotspot (Recommended)

Use the Mac as a Wi-Fi hotspot. The EVK connects to the Mac's hotspot, creating a private LAN. The Mac bridges to NTU Wi-Fi for internet access.

```
                         NTU Wi-Fi (internet only)
                               │
                    ┌──────────┴──────────┐
                    │     Mac Laptop       │
                    │  (hotspot + SSH)     │
                    │  IP: 192.168.x.1    │
                    └──────────┬──────────┘
                               │  Mac Hotspot (private LAN)
                    ┌──────────┴──────────┐
                    │   i.MX 8M Plus EVK  │
                    │   IP: 192.168.x.y   │
                    │   (auto via DHCP)    │
                    └─────────────────────┘
```

### Alternative: Portable Router

A pocket router (e.g., GL.iNet GL-MT3000) creates an independent private Wi-Fi network. Both Mac and EVK join it.

- Pros: Dedicated network, no Mac hotspot battery drain
- Cons: Extra device to carry, extra cost (~SGD 80–100)

### Alternative: USB Ethernet Direct Link

Connect Mac and EVK with a USB-to-Ethernet adapter + Ethernet cable. No Wi-Fi involved.

- Pros: Most reliable, zero network setup
- Cons: Need to carry adapter + cable, manual IP configuration

## Step-by-Step Setup

### Step 1 — Power On the EVK

1. Connect the USB-C cable from the **Anker power bank** to the EVK's **J5** connector (Port0, nearest to the corner).
2. Slide **SW3** to ON.
3. Wait **~30 seconds** for Linux to boot and Wi-Fi to auto-start.

> The EVK has `wifi-connect.service` enabled, which runs `wpa_supplicant` and attempts to connect to the last configured network on boot.

### Step 2 — Enable Mac Hotspot

**macOS Ventura / Sonoma / Sequoia:**

1. Open **System Settings → General → Sharing → Internet Sharing**
2. Share your connection from: **Wi-Fi** (NTU Wi-Fi, or your phone's hotspot)
3. To computers using: **Wi-Fi**
4. Click **Wi-Fi Options**:
   - Network Name: `EVK-Lab` (or any name you like)
   - Security: **WPA2/WPA3 Personal**
   - Password: choose a password (e.g., `evk12345`)
   - Channel: leave on auto
5. Toggle **Internet Sharing** to **ON**

**Verify the hotspot is active:**

```bash
# On the Mac, check the hotspot interface IP
ifconfig bridge100
# You should see something like: inet 192.168.2.1
```

The Mac hotspot typically assigns IPs in the `192.168.2.x` range.

### Step 3 — Configure EVK to Connect to Mac Hotspot

> **First-time only.** After this, the EVK will auto-connect on boot.

You need to tell the EVK's Wi-Fi to connect to your Mac hotspot instead of your home router. There are two ways to do this:

**Option A — Via serial console (if you have the micro-USB cable):**

Connect the micro-USB cable from **J23** to the Mac. On macOS:

```bash
# Find the serial device (3rd port = A53 console)
ls /dev/tty.usbmodem*
# or
ls /dev/cu.usbserial*

# Connect (115200 baud, the 3rd port)
screen /dev/cu.usbserial-XXXX3 115200
# or if using tty.usbmodem:
screen /dev/tty.usbmodem-XXXX3 115200
```

Press Enter to get a shell prompt, then configure Wi-Fi:

```bash
# Create or edit the wpa_supplicant config
cat > /etc/wpa_supplicant/wpa_supplicant-mlan0.conf << 'EOF'
ctrl_interface=/var/run/wpa_supplicant
update_config=1

# Mac hotspot (priority 10 = highest)
network={
    ssid="EVK-Lab"
    psk="evk12345"
    priority=10
}

# Home router (fallback)
network={
    ssid="YourHomeSSID"
    psk="YourHomePassword"
    priority=5
}
EOF

# Restart Wi-Fi
systemctl restart wifi-connect.service
# or manually:
wpa_supplicant -B -i mlan0 -c /etc/wpa_supplicant/wpa_supplicant-mlan0.conf
udhcpc -i mlan0
```

**Option B — Pre-configure at home before going to the lab:**

SSH into the EVK on your home network and add the Mac hotspot as a second network. The EVK will try the highest-priority network first.

```bash
# From your Windows PC at home
ssh root@192.168.1.98

# Add Mac hotspot credentials (on the EVK)
wpa_cli -i mlan0
> add_network
> set_network 1 ssid "EVK-Lab"
> set_network 1 psk "evk12345"
> set_network 1 priority 10
> save_config
> quit
```

### Step 4 — Find the EVK's IP Address

Once the EVK connects to your Mac hotspot, find its IP:

```bash
# On the Mac — check DHCP leases
cat /var/db/dhcpd_leases
# Look for the EVK's hostname or MAC address

# Or scan the local network
arp -a | grep bridge100

# Or use a quick nmap scan (install with: brew install nmap)
nmap -sn 192.168.2.0/24
```

Typical result: EVK gets `192.168.2.2` or similar.

### Step 5 — SSH into the EVK

```bash
# First connection (accept the host key)
ssh root@192.168.2.2
# Type "yes" when prompted about the fingerprint
# No password needed (root login enabled by default)

# You're now on the EVK!
uname -a
# Linux imx8mpevk 6.6.52-lts ...
```

**Pro tip — Add an SSH alias for convenience:**

```bash
# Add to ~/.ssh/config on Mac
cat >> ~/.ssh/config << 'EOF'

Host evk
    HostName 192.168.2.2
    User root
    StrictHostKeyChecking no
    ConnectTimeout 5
EOF

# Now just type:
ssh evk
```

### Step 6 — Verify Everything Works

```bash
# From the Mac terminal:

# 1. Check connectivity
ping -c 3 192.168.2.2

# 2. Run a command remotely
ssh evk "cat /proc/cpuinfo | head -5"

# 3. Transfer a file to the EVK
scp my_script.py evk:/opt/

# 4. Transfer a file from the EVK
scp evk:/opt/models/detect.tflite ./

# 5. Check sensors (I2C bus scan)
ssh evk "i2cdetect -y 2"

# 6. Run the detection app
ssh evk "XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1 python3 -u /opt/camera-detect/detect_camera.py --mode detect"
```

## Common Operations

### File Transfer (SCP)

```bash
# Copy a single file to the EVK
scp local_file.py evk:/opt/camera-detect/

# Copy a directory recursively
scp -r ./my_app/ evk:/opt/my_app/

# Copy from EVK to Mac
scp evk:/var/log/messages ./evk_log.txt

# Copy a large model file (shows progress)
scp -v model.tflite evk:/opt/models/
```

### Remote Command Execution

```bash
# Run a single command
ssh evk "ls -la /opt/models/"

# Run multiple commands
ssh evk "cd /opt/camera-detect && python3 -u detect_camera.py --mode detect --no-display"

# Run in background (won't stop when SSH disconnects)
ssh evk "nohup python3 -u /opt/camera-detect/detect_camera.py --mode detect > /tmp/detect.log 2>&1 &"

# Check the background process later
ssh evk "cat /tmp/detect.log | tail -20"

# Kill a background process
ssh evk "pkill -f detect_camera"
```

### I2C Sensor Operations

```bash
# List all I2C buses
ssh evk "i2cdetect -l"

# Scan I2C3 bus (expansion header J21, pins 3+5)
ssh evk "i2cdetect -y 2"

# Read a register from a sensor (e.g., BME280 chip ID at register 0xD0)
ssh evk "i2cget -y 2 0x76 0xd0"
# Expected: 0x60 (BME280) or 0x58 (BMP280)

# Read temperature from sysfs (if kernel driver is loaded)
ssh evk "cat /sys/bus/i2c/devices/2-0076/iio:device*/in_temp_input"
```

### Kernel Module Operations

```bash
# Copy module to EVK
scp kernel-modules/bme280/bme280_i2c.ko evk:/tmp/

# Load the module
ssh evk "insmod /tmp/bme280_i2c.ko"

# Check kernel log
ssh evk "dmesg | tail -10"

# Unload the module
ssh evk "rmmod bme280_i2c"
```

### Display & Camera

```bash
# Start camera preview on HDMI (must have HDMI connected)
ssh evk "XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1 gst-launch-1.0 v4l2src device=/dev/video3 ! video/x-raw,width=640,height=480 ! waylandsink &"

# Take a screenshot of the Weston desktop
ssh evk "XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1 grim /tmp/screenshot.png" 2>/dev/null
scp evk:/tmp/screenshot.png ./

# Restart Weston (if display is frozen)
ssh evk "systemctl restart weston.service"
```

### System Monitoring

```bash
# CPU temperature
ssh evk "cat /sys/class/thermal/thermal_zone0/temp"
# Divide by 1000 for °C

# Memory usage
ssh evk "free -h"

# Disk space
ssh evk "df -h /"

# Running processes
ssh evk "top -bn1 | head -15"

# Wi-Fi signal strength
ssh evk "iw dev mlan0 link"
```

## Serial Console from Mac

If Wi-Fi is not working (first boot, misconfigured network, etc.), fall back to the serial console.

### Setup

1. Connect the **micro-USB cable** from EVK **J23** to the Mac.
2. The FTDI chip creates **4 serial ports**. The **3rd port** is the A53 Linux console.

```bash
# List serial devices
ls /dev/cu.usbserial-*

# Example output:
# /dev/cu.usbserial-14101   ← 1st port (M7)
# /dev/cu.usbserial-14103   ← 2nd port
# /dev/cu.usbserial-14105   ← 3rd port (A53 Linux) ★
# /dev/cu.usbserial-14107   ← 4th port

# Connect using screen (built-in)
screen /dev/cu.usbserial-14105 115200

# Or install minicom (more features)
brew install minicom
minicom -D /dev/cu.usbserial-14105 -b 115200
```

### Screen Tips

| Action | Keys |
|--------|------|
| Exit screen | `Ctrl-A` then `K`, then `Y` |
| Scroll up | `Ctrl-A` then `Esc`, then arrow keys |
| Detach (keep session) | `Ctrl-A` then `D` |
| Reattach | `screen -r` |

> **Warning:** Don't paste long commands into the serial console — it will truncate. Use SSH for long commands or file transfers.

## Troubleshooting

### EVK won't power on with the power bank

| Symptom | Cause | Fix |
|---------|-------|-----|
| No LEDs on EVK | Power bank PD output < 45 W | Use a ≥ 45 W power bank |
| LEDs blink then off | Cable doesn't support PD | Use a PD-rated USB-C cable (≥ 60 W) |
| Power bank shows 0 W output | Wrong port on power bank | Use the **USB-C output** port (not input-only) |
| EVK boots but crashes under load | Power bank dips under load | Use a higher-wattage power bank |

### Can't find EVK on the network

```bash
# 1. Is the Mac hotspot active?
ifconfig bridge100
# Should show an IP like 192.168.2.1

# 2. Scan for devices
arp -a | grep 192.168.2

# 3. If no devices found, the EVK might not have connected.
#    Check via serial console:
ssh evk "wpa_cli -i mlan0 status"
#    Look for: wpa_state=COMPLETED

# 4. If wpa_state is not COMPLETED, reconfigure:
ssh evk "wpa_cli -i mlan0 reconfigure"
```

### SSH connection refused or timeout

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Connection refused` | SSHD not running | `ssh evk "systemctl start sshd"` (via serial) |
| `Connection timed out` | Wrong IP or network isolation | Verify with `arp -a`, check hotspot is ON |
| `Host key verification failed` | EVK IP changed, old key cached | `ssh-keygen -R 192.168.2.2` |
| Slow connection (~30s delay) | DNS reverse lookup timeout | Add `UseDNS no` to EVK's `/etc/ssh/sshd_config` |

### Wi-Fi keeps disconnecting

```bash
# Check signal strength
ssh evk "iw dev mlan0 link"
# RSSI should be > -70 dBm

# Check driver status
ssh evk "dmesg | grep -i mlan | tail -5"

# Restart Wi-Fi stack
ssh evk "systemctl restart wifi-connect.service"

# Nuclear option: reload the Wi-Fi driver
ssh evk "modprobe -r moal && modprobe moal mod_para=nxp/wifi_mod_para.conf"
```

## Quick Reference Card

Print this and tape it to your power bank:

```
╔══════════════════════════════════════════════════════╗
║  i.MX8MP EVK — Mac Portable Debug Quick Reference   ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  POWER:  USB-C PD ≥ 45W → J5 (Port0), then SW3 ON  ║
║  BOOT:   SW4 = OFF OFF ON ON (SD card)              ║
║  WAIT:   ~30 seconds for Linux + Wi-Fi              ║
║                                                      ║
║  CONNECT:                                            ║
║    Mac hotspot: "EVK-Lab" / "evk12345"              ║
║    Find IP:  arp -a | grep bridge100                ║
║    SSH:      ssh root@192.168.2.x                   ║
║    SCP:      scp file.py root@192.168.2.x:/opt/    ║
║                                                      ║
║  SERIAL (fallback):                                  ║
║    J23 micro-USB → Mac                              ║
║    screen /dev/cu.usbserial-*5 115200               ║
║    (3rd port = A53 console)                          ║
║                                                      ║
║  SENSORS:                                            ║
║    I2C3 scan:  i2cdetect -y 2                       ║
║    Read reg:   i2cget -y 2 <addr> <reg>             ║
║    J21 pins:   3=SDA, 5=SCL, 1=3.3V, 6=GND         ║
║                                                      ║
║  CAMERA:                                             ║
║    ssh evk "XDG_RUNTIME_DIR=/run/user/0             ║
║    WAYLAND_DISPLAY=wayland-1 python3 -u             ║
║    /opt/camera-detect/detect_camera.py"              ║
║                                                      ║
║  EMERGENCY:                                          ║
║    Weston frozen: systemctl restart weston.service  ║
║    Wi-Fi down:  systemctl restart wifi-connect      ║
║    Kernel log:  dmesg | tail -20                    ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
```
