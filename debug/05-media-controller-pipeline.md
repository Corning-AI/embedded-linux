# Camera requires media controller pipeline setup

## Problem

Opening `/dev/video3` directly with V4L2 capture returns -EPIPE or empty buffers. Unlike USB cameras or simple SoC cameras, the ISI capture node doesn't produce frames by itself.

## Background

i.MX8MP uses the **media controller architecture** (MC API). The camera pipeline is a graph of interconnected hardware blocks, each represented as a separate V4L2 entity. Frames flow through the graph only when all links are configured and formats match at every pad.

```
root@imx8mpevk:~# media-ctl -d /dev/media0 -p

- entity 31: ov5640 1-003c (1 pad, 1 link)
        type V4L2 subdev subtype Sensor
        pad0: Source
                [stream:0 fmt:UYVY8_1X16/640x480@1/30]
                -> "mxc-mipi-csi2.0":0 [ENABLED,IMMUTABLE]

- entity 22: mxc-mipi-csi2.0 (8 pads, 2 links)
        pad0: Sink
                <- "ov5640 1-003c":0 [ENABLED,IMMUTABLE]
        pad4: Source
                -> "mxc_isi.0":0 [ENABLED]

- entity 1: mxc_isi.0 (16 pads, 2 links)
        pad0: Sink
                <- "mxc-mipi-csi2.0":4 [ENABLED]
        pad12: Source
                -> "mxc_isi.0.capture":0 [ENABLED]

- entity 18: mxc_isi.0.capture (1 pad, 1 link)
        device node name /dev/video3
        pad0: Sink
                <- "mxc_isi.0":12 [ENABLED]
```

## Pipeline

```
ov5640 (sensor) → mipi-csi2 (deserializer) → isi.0 (DMA engine) → /dev/video3
```

On this EVK, the links come up pre-configured (ENABLED, some IMMUTABLE) so the pipeline works without manual `media-ctl` link setup. But format propagation still matters.

## Setting formats

If you need to change resolution or pixel format, you must configure each entity from source to sink:

```bash
# Set sensor output
media-ctl -d /dev/media0 --set-v4l2 \
    '"ov5640 1-003c":0[fmt:UYVY8_1X16/1920x1080@1/30]'

# Set MIPI receiver output (must match sensor)
media-ctl -d /dev/media0 --set-v4l2 \
    '"mxc-mipi-csi2.0":4[fmt:UYVY8_1X16/1920x1080]'

# Set ISI input
media-ctl -d /dev/media0 --set-v4l2 \
    '"mxc_isi.0":0[fmt:UYVY8_1X16/1920x1080]'
```

Then set the capture format on `/dev/video3` via `v4l2-ctl` or `VIDIOC_S_FMT`. The ISI does the final YUV→RGB conversion in hardware.

## Key insight

On simple cameras (USB webcam), you just open the device and set the format. On SoC camera subsystems, you're configuring a hardware graph. Each node has input/output pads with format constraints. A format mismatch at any point in the chain breaks the entire pipeline.

GStreamer's `v4l2src` handles the `/dev/video3` capture side, but it does NOT configure the media controller pipeline. That's a separate step, either via `media-ctl` or programmatically via the MC ioctls.
