# /dev/video0 is NOT the camera

## Problem

After booting imx-image-multimedia on the i.MX8MP EVK with an OV5640 connected to J12, the standard approach of opening `/dev/video0` for camera capture fails silently or returns VPU encoder data.

## Investigation

```
root@imx8mpevk:~# v4l2-ctl --list-devices
 ():
        /dev/v4l-subdev0

FSL Capture Media Device (platform:32c00000.bus:camera):
        /dev/media0

mxc-isi-cap_v1 (platform:32e00000.isi:cap_devic):
        /dev/video3

mxc-isi-m2m_v1 (platform:32e00000.isi:m2m_devic):
        /dev/video2

vsi_v4l2dec (platform:vsi_v4l2dec):
        /dev/video1

vsi_v4l2enc (platform:vsi_v4l2enc):
        /dev/video0
```

The VPU encoder/decoder register first during boot and grab video0/video1. The ISI (Image Sensing Interface) registers later and gets video2/video3.

## Root cause

V4L2 device numbering is **probe order dependent**, not semantically assigned. On i.MX8MP:

| Device | Driver | Function |
| ------ | ------ | -------- |
| /dev/video0 | vsi_v4l2enc | VPU H.264/HEVC encoder |
| /dev/video1 | vsi_v4l2dec | VPU decoder |
| /dev/video2 | mxc-isi-m2m | ISI color space conversion |
| /dev/video3 | mxc-isi-cap | ISI capture — **this is the camera** |

## Fix

Always use `v4l2-ctl --list-devices` to find the correct node. For scripting, filter by driver name:

```bash
v4l2-ctl --list-devices 2>/dev/null | grep -A1 "mxc-isi-cap" | tail -1 | tr -d '\t'
```

This is a common pitfall on SoCs with multiple V4L2 subsystems. The NXP documentation sometimes assumes video0 because their minimal image doesn't include VPU drivers.
