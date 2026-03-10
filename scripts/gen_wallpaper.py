#!/usr/bin/env python3
"""Apple-authentic dark wallpaper for i.MX8MP EVK — v10.
Dr. Ning Kang — Research Fellow, NTU Singapore.
Color: Apple system dark (#000000–#1C1C1E) + accent blue #0A84FF.
Nearly pure black background — premium comes from restraint, not color.
Top area clean for sensor data overlay.
"""

import math
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080

img = Image.new("RGB", (W, H))
pixels = img.load()

# ================================================================
# BACKGROUND: Apple dark mode — near-black with barely visible depth
# Not colored. Not warm. Not cold. Just dark with subtle dimension.
# ================================================================
for y in range(H):
    for x in range(W):
        nx, ny = x / W, y / H

        # Base: Apple systemBackground dark (#000000 to #1C1C1E range)
        # Subtle radial vignette: slightly lighter center, darker edges
        cx, cy = 0.5, 0.55
        dist = math.sqrt((nx - cx) ** 2 + ((ny - cy) * 0.8) ** 2)
        vignette = max(0, 1 - dist * 1.2)

        # Very subtle elevation: just enough to not be flat pure black
        base = 4 + int(18 * vignette)  # ranges from 4 to 22

        # Barely perceptible cool undertone (Apple's dark has slight blue)
        r = base
        g = base
        b = base + int(3 * vignette)  # +3 max blue, barely noticeable

        pixels[x, y] = (r, g, b)

img = img.filter(ImageFilter.GaussianBlur(radius=3))
pixels = img.load()

# Subtle noise (prevents banding on dark gradients — critical for quality)
random.seed(42)
for _ in range(80000):
    x = random.randint(0, W - 1)
    y = random.randint(0, H - 1)
    r, g, b = pixels[x, y]
    n = random.randint(-2, 2)
    pixels[x, y] = (max(0, r + n), max(0, g + n), max(0, b + n))

draw = ImageDraw.Draw(img)

# ================================================================
# FONTS — Segoe UI Light (closest to SF Pro on Windows)
# ================================================================
try:
    f_hero = ImageFont.truetype("segoeuil.ttf", 62)
    f_title = ImageFont.truetype("segoeuil.ttf", 22)
    f_body = ImageFont.truetype("segoeui.ttf", 15)
    f_small = ImageFont.truetype("segoeui.ttf", 13)
    f_tiny = ImageFont.truetype("segoeui.ttf", 11)
except OSError:
    f_hero = ImageFont.truetype("arial.ttf", 62)
    f_title = ImageFont.truetype("arial.ttf", 22)
    f_body = ImageFont.truetype("arial.ttf", 15)
    f_small = ImageFont.truetype("arial.ttf", 13)
    f_tiny = ImageFont.truetype("arial.ttf", 11)

# Apple dark mode text colors (official)
WHITE = (255, 255, 255)                  # primary text
SECONDARY = (152, 152, 157)              # gray1 — secondary text
TERTIARY = (99, 99, 102)                 # gray2 — tertiary
QUATERNARY = (72, 72, 74)                # gray3 — quaternary
ACCENT_BLUE = (10, 132, 255)             # Apple system blue (dark)
ACCENT_TEAL = (100, 210, 255)            # Apple teal (dark)
ACCENT_INDIGO = (94, 92, 230)            # Apple indigo (dark)

# ================================================================
# BOTTOM SECTION: Name + info (bottom 28%)
# ================================================================

# Subtle separator line at 72% height
sep_y = int(H * 0.72)
sep_margin = 400
for sx in range(sep_margin, W - sep_margin):
    progress = (sx - sep_margin) / (W - 2 * sep_margin)
    a = int(20 * math.sin(progress * math.pi))
    pr, pg, pb = pixels[sx, sep_y]
    pixels[sx, sep_y] = (pr + a, pg + a, pb + a)
draw = ImageDraw.Draw(img)

# --- Hero name ---
name = "Dr. Ning Kang"
name_bbox = draw.textbbox((0, 0), name, font=f_hero)
name_w = name_bbox[2] - name_bbox[0]
name_x = (W - name_w) // 2
name_y = int(H * 0.76)
draw.text((name_x, name_y), name, fill=WHITE, font=f_hero)

# --- Title (Apple secondary gray) ---
title = "Research Fellow  |  NTU Singapore"
t_bbox = draw.textbbox((0, 0), title, font=f_title)
t_x = (W - (t_bbox[2] - t_bbox[0])) // 2
t_y = name_y + 72
draw.text((t_x, t_y), title, fill=SECONDARY, font=f_title)

# --- Keywords with Apple accent colors ---
# Use centered dot-separated keywords with color highlights
kw_y = t_y + 40
kw_parts = [
    ("Wireless Power Transfer", SECONDARY),
    ("  ·  ", QUATERNARY),
    ("FPGA", SECONDARY),
    ("  ·  ", QUATERNARY),
    ("Embedded Linux", SECONDARY),
    ("  ·  ", QUATERNARY),
    ("Power Electronics", SECONDARY),
]

# Calculate total width
total_kw_w = sum(draw.textlength(text, font=f_body) for text, _ in kw_parts)
kw_x = (W - total_kw_w) / 2
for text, color in kw_parts:
    draw.text((kw_x, kw_y), text, fill=color, font=f_body)
    kw_x += draw.textlength(text, font=f_body)

# --- Stats ---
st_y = kw_y + 26
st_parts = [
    ("PhD (SJTU)", TERTIARY),
    ("  ·  ", QUATERNARY),
    ("200+ Citations", TERTIARY),
    ("  ·  ", QUATERNARY),
    ("7 IEEE Papers", TERTIARY),
]
total_st_w = sum(draw.textlength(t, font=f_small) for t, _ in st_parts)
st_x = (W - total_st_w) / 2
for text, color in st_parts:
    draw.text((st_x, st_y), text, fill=color, font=f_small)
    st_x += draw.textlength(text, font=f_small)

# ================================================================
# TOP-LEFT: System specs (Apple quaternary — barely visible)
# ================================================================
draw.text((60, 36), "i.MX8MP EVK", fill=SECONDARY, font=f_body)
draw.text((60, 58), "Linux 6.6.52  ·  NPU 2.3 TOPS  ·  WiFi  ·  BT 5.4", fill=TERTIARY, font=f_small)

# ================================================================
# TOP-RIGHT: Sensor area label
# ================================================================
sa = "// SENSOR DATA"
sa_bbox = draw.textbbox((0, 0), sa, font=f_small)
draw.text((W - 60 - (sa_bbox[2] - sa_bbox[0]), 36), sa, fill=QUATERNARY, font=f_small)

# ================================================================
# BOTTOM-RIGHT: GitHub
# ================================================================
gh = "github.com/Corning-AI/embedded-linux"
gh_bbox = draw.textbbox((0, 0), gh, font=f_tiny)
draw.text((W - 60 - (gh_bbox[2] - gh_bbox[0]), H - 32), gh, fill=(42, 42, 44), font=f_tiny)

# ================================================================
# Save
# ================================================================
out = r"c:\Users\corni\OneDrive - Nanyang Technological University\ntu_rf\M266_EmbeddedLinux\scripts\evk_wallpaper.png"
img.save(out, "PNG", optimize=False)

import os
print(f"Saved: {out}")
print(f"Resolution: {W}x{H}, Size: {os.path.getsize(out) / 1024:.0f} KB")
