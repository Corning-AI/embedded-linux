# Camera preview has red/blue color shift

## Symptom

GStreamer pipeline outputs live video to HDMI but the entire image has a strong red tint:

```bash
gst-launch-1.0 v4l2src device=/dev/video3 ! \
    video/x-raw,width=640,height=480,framerate=30/1 ! \
    autovideosink
```

Video plays fine, frame rate is stable, but colors are completely off — skin tones look red, white objects look pink.

## Analysis

Checked the ISI capture format negotiation:

```
root@imx8mpevk:~# v4l2-ctl -d /dev/video3 --list-formats-ext
ioctl: VIDIOC_ENUM_FMT
        Type: Video Capture Multiplanar
        [0]: 'RGBP' (16-bit RGB 5-6-5)
        [1]: 'RGB3' (24-bit RGB 8-8-8)
        [2]: 'BGR3' (24-bit BGR 8-8-8)
        ...
```

The ISI supports both RGB and BGR output formats. Without explicit format negotiation, `autovideosink` (which picks `waylandsink` under Weston) may request RGB while the ISI delivers BGR, or vice versa. The R and B channels get swapped, producing the red tint.

## Root cause

The ISI capture node's default pixel format doesn't match what the Wayland compositor expects. The media controller pipeline does format conversion in hardware, but the output color channel ordering depends on the negotiated format between v4l2src and the sink.

## Fix

Insert `videoconvert` between source and sink to handle the RGB↔BGR conversion:

```bash
gst-launch-1.0 v4l2src device=/dev/video3 ! \
    video/x-raw,width=640,height=480,framerate=30/1 ! \
    videoconvert ! autovideosink
```

`videoconvert` inspects both sides, determines the actual format mismatch, and does CPU-based channel reordering. Alternatively, force a specific format on the v4l2src side:

```bash
gst-launch-1.0 v4l2src device=/dev/video3 ! \
    video/x-raw,format=BGR,width=640,height=480 ! \
    videoconvert ! waylandsink
```

## Notes

This only affects the ISI capture path. When using NXP's `imxv4l2src` element (from `imx-gst1.0-plugin`), the format negotiation is handled internally and the color shift doesn't occur.
