# Weston service name: weston.service, not weston@root

## Problem

Following various NXP guides to start the Wayland compositor:

```
root@imx8mpevk:~# systemctl start weston@root
Failed to start weston@root.service: Unit weston@root.service not found.
```

Several NXP community posts and older BSP docs reference `weston@root` as the service unit name.

## Investigation

```
root@imx8mpevk:~# systemctl list-units | grep weston
weston.service    loaded active running    Weston Wayland Compositor

root@imx8mpevk:~# systemctl status weston.service
● weston.service - Weston Wayland Compositor
     Loaded: loaded (/lib/systemd/system/weston.service)
     Active: active (running)
```

## Root cause

The Weston systemd unit naming changed between Yocto releases:

- **Zeus/Dunfell (older):** `weston@root.service` — template unit, instantiated per user
- **Kirkstone and later:** `weston.service` — regular unit, runs as root by default

The `@` template pattern was dropped because in embedded use cases Weston almost always runs as root with XDG_RUNTIME_DIR=/run/user/0.

## Fix

```bash
# Correct for Scarthgap (kernel 6.6):
systemctl start weston.service
systemctl status weston.service

# For GStreamer to find the Wayland display:
export XDG_RUNTIME_DIR=/run/user/0
```

## Note

If running GStreamer pipelines over SSH or serial, always set `XDG_RUNTIME_DIR` first. Without it, `waylandsink` can't connect to the Weston compositor and falls back to fbdev or fails entirely.
