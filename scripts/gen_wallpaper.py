#!/usr/bin/env python3
"""Generate a tech-themed wallpaper for i.MX8MP EVK desktop.
Reflects: FPGA, Embedded Linux, Power Electronics, Engineering dreams.
"""

import math
import random
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
random.seed(42)  # reproducible

img = Image.new("RGB", (W, H))
draw = ImageDraw.Draw(img)

# --- Dark gradient background (deep navy to dark teal) ---
for y in range(H):
    r = int(8 + 12 * (y / H))
    g = int(15 + 25 * (y / H))
    b = int(30 + 35 * (y / H))
    draw.line([(0, y), (W, y)], fill=(r, g, b))

# --- Circuit trace grid pattern ---
trace_color = (30, 55, 80)
dot_color = (50, 90, 130)

# horizontal traces
for y in range(60, H, 80):
    jitter = random.randint(-2, 2)
    segments = random.randint(2, 5)
    x_points = sorted(random.sample(range(100, W - 100), segments * 2))
    for i in range(0, len(x_points) - 1, 2):
        draw.line([(x_points[i], y + jitter), (x_points[i + 1], y + jitter)],
                  fill=trace_color, width=1)

# vertical traces
for x in range(80, W, 100):
    jitter = random.randint(-2, 2)
    segments = random.randint(2, 4)
    y_points = sorted(random.sample(range(80, H - 80), segments * 2))
    for i in range(0, len(y_points) - 1, 2):
        draw.line([(x + jitter, y_points[i]), (x + jitter, y_points[i + 1])],
                  fill=trace_color, width=1)

# via dots at some intersections
for _ in range(120):
    x = random.randint(80, W - 80)
    y = random.randint(60, H - 60)
    r = random.choice([2, 3])
    draw.ellipse([x - r, y - r, x + r, y + r], fill=dot_color)
    draw.ellipse([x - r - 2, y - r - 2, x + r + 2, y + r + 2], outline=trace_color)

# --- Glowing accent circles (like IC pads) ---
for _ in range(8):
    cx = random.randint(200, W - 200)
    cy = random.randint(150, H - 150)
    for radius in range(25, 0, -1):
        alpha = int(5 * (25 - radius) / 25)
        c = (20 + alpha * 3, 60 + alpha * 4, 100 + alpha * 5)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=c)

# --- Waveform (sine wave - represents signals/power electronics) ---
wave_y_center = H // 2 + 50
for phase_offset, color, amp in [
    (0, (0, 180, 220, 80), 40),
    (math.pi / 3, (0, 220, 180, 60), 30),
    (math.pi * 2 / 3, (100, 200, 255, 50), 25),
]:
    points = []
    for x in range(0, W, 2):
        y = wave_y_center + int(amp * math.sin(x * 0.008 + phase_offset))
        points.append((x, y))
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=color[:3], width=1)

# --- Binary rain (subtle, matrix-style but tasteful) ---
binary_font_size = 11
try:
    small_font = ImageFont.truetype("consola.ttf", binary_font_size)
except:
    small_font = ImageFont.load_default()

for _ in range(200):
    x = random.randint(0, W)
    y = random.randint(0, H)
    bit = random.choice(["0", "1"])
    brightness = random.randint(20, 45)
    draw.text((x, y), bit, fill=(0, brightness, brightness + 10), font=small_font)

# --- Main title text ---
try:
    title_font = ImageFont.truetype("consola.ttf", 42)
    sub_font = ImageFont.truetype("consola.ttf", 20)
    quote_font = ImageFont.truetype("consola.ttf", 16)
    tag_font = ImageFont.truetype("consola.ttf", 14)
except:
    title_font = ImageFont.load_default()
    sub_font = title_font
    quote_font = title_font
    tag_font = title_font

# Title block (bottom-right area)
tx, ty = W - 620, H - 280

# Subtle background box
for yy in range(ty - 20, ty + 230):
    for xx in range(tx - 30, tx + 580):
        if 0 <= xx < W and 0 <= yy < H:
            pr, pg, pb = img.getpixel((xx, yy))
            img.putpixel((xx, yy), (pr // 2, pg // 2, pb // 2))

# Accent line
draw.line([(tx - 20, ty), (tx + 560, ty)], fill=(0, 180, 220), width=2)

draw.text((tx, ty + 15), "i.MX8MP EVK", fill=(0, 200, 240), font=title_font)
draw.text((tx, ty + 65), "Embedded Linux  |  NPU  |  FPGA", fill=(120, 180, 210), font=sub_font)
draw.text((tx, ty + 95), "Power Electronics  |  Motor Control", fill=(120, 180, 210), font=sub_font)

# Inspirational quote
draw.text((tx, ty + 140), '"The best way to predict the future', fill=(80, 140, 170), font=quote_font)
draw.text((tx, ty + 160), ' is to engineer it."', fill=(80, 140, 170), font=quote_font)

# Tag line
draw.text((tx, ty + 195), "NTU M266  //  PhD  //  Senior Firmware Engineer", fill=(60, 110, 140), font=tag_font)

# --- Top-left system info area ---
lx, ly = 40, 30
draw.text((lx, ly), "// SYSTEM", fill=(0, 150, 180), font=sub_font)
info_lines = [
    "SoC     : NXP i.MX8M Plus (Cortex-A53 + M7 + NPU)",
    "Kernel  : Linux 6.6.52-lts",
    "GPU     : Vivante GC7000UL",
    "NPU     : 2.3 TOPS INT8",
    "WiFi/BT : NXP 88W8997 (PCIe + UART)",
    "Camera  : OV5640 MIPI-CSI2",
]
for i, line in enumerate(info_lines):
    draw.text((lx, ly + 30 + i * 22), line, fill=(50, 100, 130), font=tag_font)

# --- Save ---
out_path = r"c:\Users\corni\OneDrive - Nanyang Technological University\ntu_rf\M266_EmbeddedLinux\scripts\evk_wallpaper.png"
img.save(out_path, "PNG")
print(f"Wallpaper saved: {out_path}")
print(f"Size: {W}x{H}")
