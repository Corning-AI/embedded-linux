# 06 — Wi-Fi & Bluetooth Bring-Up

Debugging log for enabling Wi-Fi and Bluetooth on the i.MX 8M Plus EVK. The on-board wireless module (AzureWave AW-CM276NF) is **not enabled by default** in the NXP Yocto scarthgap BSP — the stock device tree has PCIe disabled, and no overlay is provided to turn it on.

This document records the full investigation: a failed SDIO attempt, physical inspection that revealed the actual interface, a surgical DTB binary patch, and the final working configuration for both Wi-Fi (PCIe) and Bluetooth (UART).

## Hardware Identification

### Module & Carrier Board

| Component | Part Number | Notes |
|-----------|-------------|-------|
| Wi-Fi/BT Module | AzureWave AW-CM276NF | NXP 88W8997 chipset, 2x2 802.11ac + BT 5.1 |
| Carrier Board | AzureWave AW-CM276MA | Labeled "PCIE-UART" — routes PCIe + UART from module to M.2 |
| EVK Slot | J10 (M.2 Key-E) | Under the heatsink, near the PMIC area |
| Antennas | 2x U.FL → SMA | Main + Aux, connected to pigtail cables on EVK |

### Interface Architecture

The **AW-CM276MA carrier board** is the key detail that NXP's documentation glosses over:

```
AW-CM276NF Module (88W8997)
├── Wi-Fi  ──→  PCIe lane  ──→  AW-CM276MA carrier  ──→  M.2 Key-E (J10)  ──→  i.MX8MP PCIe RC
└── BT     ──→  UART pins  ──→  AW-CM276MA carrier  ──→  M.2 Key-E (J10)  ──→  i.MX8MP UART3
```

- **Wi-Fi uses PCIe** (not SDIO) — this is the critical fact that cost me hours of debugging
- **Bluetooth uses UART3** (`/dev/ttymxc2`, base address `0x30880000`)

## Debugging Methodology

All commands were sent to the EVK over the debug UART (J23 → COM5 at 115200 baud) using automated PowerShell scripts. This approach is faster and more repeatable than typing commands manually in a serial terminal.

### Serial Automation Framework

```powershell
# Reusable pattern for all debug scripts
$port = New-Object System.IO.Ports.SerialPort 'COM5', 115200, 'None', 8, 'One'
$port.ReadTimeout = 2000
$port.Open()

# Flush stale data
Start-Sleep -Milliseconds 500
$port.DiscardInBuffer()
$port.Write("`r`n")
Start-Sleep -Milliseconds 1000

# Send command and capture output
$port.Write("your_command_here`r`n")
Start-Sleep -Milliseconds 3000
for ($j = 0; $j -lt 50; $j++) {
    try { $line = $port.ReadLine(); Write-Host $line }
    catch { break }
}

$port.Close()
```

This pattern was used in ~20 scripts throughout the debugging session, each targeting a specific hypothesis.

## Phase 1 — Failed SDIO Attempt

### Hypothesis

The AW-CM276NF might use SDIO (like many embedded Wi-Fi modules). NXP provides `imx8mp-evk-usdhc1-m2.dtb` which enables USDHC1 for an M.2 Wi-Fi module.

### Test

```bash
# Backup original DTB
cp /run/media/boot-mmcblk1p1/imx8mp-evk.dtb /run/media/boot-mmcblk1p1/imx8mp-evk.dtb.orig

# Switch to M.2 SDIO DTB
cp /run/media/boot-mmcblk1p1/imx8mp-evk-usdhc1-m2.dtb /run/media/boot-mmcblk1p1/imx8mp-evk.dtb
sync && reboot
```

### Result: FAILED

```
mmc0: error -110 whilst initialising SDIO card
mmc0: Failed to initialize a non-removable card
```

The SDIO controller found nothing. The module is not wired for SDIO.

### Key Observation

Physical inspection of the carrier board revealed **"PCIE-UART"** printed on the PCB silkscreen. This isn't just a product name — it describes the actual signal routing: **PCIe for Wi-Fi, UART for Bluetooth**.

## Phase 2 — PCIe Investigation

### DTB Analysis

```bash
# Check PCIe status in the stock device tree
$ strings /run/media/boot-mmcblk1p1/imx8mp-evk.dtb.orig | grep -c pcie
# → pcie@33800000 node exists

$ cat /sys/firmware/devicetree/base/pcie@33800000/status
disabled
```

PCIe is **explicitly disabled** in the stock DTB. No PCIe Root Complex DTB variant is provided by NXP (only `imx8mp-evk-pcie-ep.dtb` for Endpoint mode, which is the wrong direction).

### The Problem

- `fdtput` and `dtc` are **not available** on the `imx-image-multimedia` rootfs
- No DTB overlays directory exists
- The only way to enable PCIe is to patch the DTB binary directly

## Phase 3 — DTB Binary Patching

### Finding the Exact Offset

The FDT (Flattened Device Tree) binary format stores property values as null-terminated strings. I needed to find the `status = "disabled"` property belonging to `pcie@33800000` and change it to `"okay"`.

```bash
# Step 1: Find the pcie node name in the binary
$ strings -t d /run/media/boot-mmcblk1p1/imx8mp-evk.dtb.orig | grep 'pcie@33800000'
50648 pcie@33800000

# Step 2: Find all "disabled" strings near that offset
$ strings -t d /run/media/boot-mmcblk1p1/imx8mp-evk.dtb.orig | grep disabled
# Multiple hits — need to identify which one belongs to the pcie node

# Step 3: Verify the FDT_PROP structure at the candidate offset
$ python3 -c "
data = open('/run/media/boot-mmcblk1p1/imx8mp-evk.dtb.orig','rb').read()
off = 52028  # Candidate FDT_PROP header
tag = int.from_bytes(data[off:off+4], 'big')
length = int.from_bytes(data[off+4:off+8], 'big')
nameoff = int.from_bytes(data[off+8:off+12], 'big')
print(f'tag=0x{tag:08x} len={length} nameoff=0x{nameoff:04x}')
print(f'value = {data[off+12:off+12+length]}')
"
# Output: tag=0x00000003 len=9 nameoff=0x049c
# value = b'disabled\x00'
```

- `tag=0x00000003` = `FDT_PROP` (correct)
- `len=9` = length of `"disabled\0"` (correct)
- The actual string starts at offset **52040** (= 52028 + 12 bytes of header)

### Applying the Patch

```bash
# Backup current DTB
cp /run/media/boot-mmcblk1p1/imx8mp-evk.dtb /run/media/boot-mmcblk1p1/imx8mp-evk.dtb.pre-pcie-patch

# Binary patch: "disabled\0" → "okay\0\0\0\0\0" (same 9 bytes, null-padded)
python3 -c "
data = bytearray(open('/run/media/boot-mmcblk1p1/imx8mp-evk.dtb.orig','rb').read())
off = 52040
assert data[off:off+9] == b'disabled\x00', 'Safety check failed!'
data[off:off+9] = b'okay\x00\x00\x00\x00\x00'
open('/run/media/boot-mmcblk1p1/imx8mp-evk.dtb','wb').write(bytes(data))
print('Patch applied successfully')
"

# Verify
hexdump -C -s 52036 -n 16 /run/media/boot-mmcblk1p1/imx8mp-evk.dtb
# Should show: 0000cb44  00 00 04 9c 6f 6b 61 79  00 00 00 00 00 ...
#                                     o k a y  \0 \0 \0 \0 \0

sync && reboot
```

> **Why null-pad to 9 bytes?** The FDT property length field still says 9. If we wrote only `"okay\0"` (5 bytes), the remaining 4 bytes would be garbage. Padding with zeros keeps the binary structure valid without recalculating offsets.

### Result: PCIe WORKING

```bash
$ lspci
00:00.0 PCI bridge: Synopsys, Inc. DWC_usb3 / PCIe bridge (rev 01)
01:00.0 Ethernet controller: Marvell Technology Group Ltd. Device 2b42 (rev 11)
```

Device `2b42` = **NXP 88W8997** Wi-Fi/BT combo chip. PCIe Gen.2 x1 link established.

## Phase 4 — Wi-Fi Driver

### First Attempt (Failed)

```bash
$ modprobe moal fw_name=nxp/pcieuart8997_combo_v4.bin
# → WLAN FW loaded, but probe failed with error -14 (EFAULT)
```

Specifying `fw_name` alone misses other critical parameters (cfg80211_wext, host_mlme, ps_mode, etc.).

### Working Configuration

```bash
$ modprobe moal mod_para=nxp/wifi_mod_para.conf
```

The `wifi_mod_para.conf` file (shipped with the BSP) contains a `PCIE8997` config block that the driver auto-detects based on the PCIe device ID. This sets all required parameters:

```
[PCIE8997]
fw_name=nxp/pcieuart8997_combo_v4.bin
cfg80211_wext=0xf
host_mlme=1
...
```

### Result

```bash
$ ip link show mlan0
mlan0: <BROADCAST,MULTICAST> mtu 1500 qdisc noop state DOWN
    link/ether xx:xx:xx:xx:xx:xx brd ff:ff:ff:ff:ff:ff
```

Three interfaces registered: `mlan0` (station), `uap0` (AP), `wfd0` (Wi-Fi Direct).

### Connecting to a Network

```bash
# Create wpa_supplicant config
cat > /etc/wpa_supplicant-mlan0.conf << 'EOF'
ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=SG

network={
    ssid="YOUR_SSID"
    psk="YOUR_PASSWORD"
    key_mgmt=WPA-PSK
}
EOF

# Bring up interface
ip link set mlan0 up

# Start authentication
wpa_supplicant -B -i mlan0 -c /etc/wpa_supplicant-mlan0.conf -D nl80211

# Wait for association, then get IP
sleep 5
udhcpc -i mlan0

# Verify
ping -c 3 8.8.8.8
```

```
PING 8.8.8.8 (8.8.8.8): 56 data bytes
64 bytes from 8.8.8.8: seq=0 ttl=117 time=5.044 ms
64 bytes from 8.8.8.8: seq=1 ttl=117 time=5.328 ms
64 bytes from 8.8.8.8: seq=2 ttl=117 time=4.972 ms
--- 8.8.8.8 ping statistics ---
3 packets transmitted, 3 packets received, 0% packet loss
```

## Phase 5 — Bluetooth

### hciattach Approach (Failed)

```bash
$ hciattach /dev/ttymxc2 any 115200 noflow
# → Timeout, BD Address: 00:00:00:00:00:00, RX bytes: 0

$ hciattach /dev/ttymxc2 any 3000000 flow
# → Same timeout
```

The generic `hciattach` doesn't know how to:
1. Download NXP-specific firmware to the 88W8997
2. Negotiate the baud rate handshake
3. Initialize the NXP vendor-specific HCI extensions

### Kernel Config Check

```bash
$ zcat /proc/config.gz | grep -i mrvl
# CONFIG_BT_HCIUART_MRVL is not set
# CONFIG_BT_MRVL is not set
```

The Marvell BT drivers are disabled. But there's a better option:

```bash
$ find /lib/modules/$(uname -r) -name '*btnxp*'
/lib/modules/6.6.52-lts-next-g5a0a5e71d2bd/kernel/drivers/bluetooth/btnxpuart.ko
```

### Working Configuration

```bash
$ modprobe btnxpuart
```

That's it. The `btnxpuart` driver:
1. Attaches to UART3 (matched via device tree `serial@30880000` with `uart-has-rtscts`)
2. Downloads the NXP BT firmware (`uart8997_bt_v4.bin`)
3. Negotiates high-speed baud rate
4. Registers `hci0`

### Result

```bash
$ hciconfig hci0
hci0:   Type: Primary  Bus: UART
        BD Address: xx:xx:xx:xx:xx:xx  ACL MTU: 1021:5  SCO MTU: 120:6
        UP RUNNING
        ...

$ hciconfig -a hci0 | grep -E 'Name|Manufacturer|Version'
        Name: 'BlueZ 5.72'
        Manufacturer: Marvell Technology (72)
        HCI Version: 5.4 (0xd)

$ hcitool scan
Scanning ...
        xx:xx:xx:xx:xx:xx       Device-1
        xx:xx:xx:xx:xx:xx       Device-2
```

Bluetooth 5.4, classic scan and BLE both working.

## Phase 6 — Boot Persistence

### Wi-Fi Auto-Start

```bash
# 1. Module auto-load with correct parameters
echo 'options moal mod_para=nxp/wifi_mod_para.conf' > /etc/modprobe.d/moal.conf
echo moal >> /etc/modules-load.d/wifi.conf

# 2. Systemd service for connection
cat > /etc/systemd/system/wifi-connect.service << 'EOF'
[Unit]
Description=WiFi Auto Connect
After=network-pre.target
Wants=network-pre.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/sbin/modprobe moal mod_para=nxp/wifi_mod_para.conf
ExecStartPre=/bin/sleep 3
ExecStartPre=/sbin/ip link set mlan0 up
ExecStart=/usr/sbin/wpa_supplicant -B -i mlan0 -c /etc/wpa_supplicant-mlan0.conf -D nl80211
ExecStartPost=/bin/sleep 3
ExecStartPost=/sbin/udhcpc -i mlan0

[Install]
WantedBy=multi-user.target
EOF

systemctl enable wifi-connect.service
```

### Bluetooth Auto-Start

```bash
# btnxpuart auto-loads via device tree matching, but to be explicit:
echo btnxpuart >> /etc/modules-load.d/bluetooth.conf
```

### Verification After Reboot

```bash
$ systemctl status wifi-connect.service
● wifi-connect.service - WiFi Auto Connect
     Loaded: loaded (/etc/systemd/system/wifi-connect.service; enabled)
     Active: active (exited)

$ ping -c 1 8.8.8.8
64 bytes from 8.8.8.8: seq=0 ttl=117 time=5.1 ms

$ hciconfig hci0
hci0: ... UP RUNNING
```

Both Wi-Fi and Bluetooth survive reboot.

## Summary of Issues and Root Causes

| Issue | Root Cause | Solution |
|-------|-----------|----------|
| SDIO DTB fails with `mmc0: Failed to initialize` | Module uses PCIe, not SDIO | Use base DTB with PCIe enabled |
| PCIe disabled in stock DTB | NXP ships with `pcie@33800000 status = "disabled"` | Binary DTB patch at offset 52040 |
| No `fdtput`/`dtc` on board | `imx-image-multimedia` doesn't include DT tools | Use Python3 for binary patching |
| `moal fw_name=...` probe fails (-14) | Missing driver parameters | Use `mod_para=nxp/wifi_mod_para.conf` |
| `hciattach` timeout (BD 00:00:00:00:00:00) | Generic HCI doesn't do NXP firmware download | Use `btnxpuart` kernel module |
| Hybrid DTB (M2 + PCIe patch) breaks everything | Different DTB has different binary offsets | Stick with base DTB + single PCIe patch |

## Files Modified on the EVK

```
/run/media/boot-mmcblk1p1/
├── imx8mp-evk.dtb              ← patched (PCIe enabled)
├── imx8mp-evk.dtb.orig         ← original backup
└── imx8mp-evk.dtb.pre-pcie-patch ← pre-patch backup

/etc/
├── wpa_supplicant-mlan0.conf   ← WiFi credentials
├── modprobe.d/moal.conf        ← moal driver options
├── modules-load.d/
│   ├── wifi.conf               ← auto-load moal
│   └── bluetooth.conf          ← auto-load btnxpuart
└── systemd/system/
    └── wifi-connect.service    ← auto WiFi on boot
```

## Lessons Learned

1. **Read the carrier board**, not just the module datasheet. The "PCIE-UART" silkscreen on the AW-CM276MA carrier board was the single most important clue.

2. **DTB binary patching is viable** when you lack `dtc`/`fdtput`. The FDT format is well-specified — as long as the replacement string fits within the original property length, a simple byte substitution works. Python3 (often available even on minimal images) is sufficient.

3. **NXP-specific drivers exist for a reason.** The generic Linux `hciattach` and manual `fw_name=` parameter don't handle NXP's proprietary firmware download protocol. Always check for vendor-specific modules (`btnxpuart`, `moal` with `mod_para`) before falling back to generic tools.

4. **Automated serial debugging pays off.** Each hypothesis was testable with a single script run — no manual typing errors, no forgotten commands, and a full log of every attempt. Over ~20 scripts, this saved significant time compared to interactive debugging.
