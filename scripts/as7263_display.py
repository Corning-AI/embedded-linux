#!/usr/bin/env python3
"""
AS7263 Real-time NIR Dashboard (GTK3 + Cairo)

Displays 6-channel spectral data, temperature, and TOI trend on HDMI.
Designed for i.MX8MP EVK with Weston compositor.
"""

import os
import sys
import time
import math
import struct
import fcntl
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

# --- I2C setup ---
I2C_SLAVE = 0x0703
ADDR = 0x49
CALS = {'R': 0x14, 'S': 0x18, 'T': 0x1C, 'U': 0x20, 'V': 0x24, 'W': 0x28}
LABELS = {
    'R': ('610nm', (1.0, 0.3, 0.3)),
    'S': ('680nm', (1.0, 0.5, 0.2)),
    'T': ('730nm', (0.9, 0.2, 0.2)),
    'U': ('760nm', (0.6, 0.3, 0.8)),
    'V': ('810nm', (0.3, 0.7, 1.0)),
    'W': ('860nm', (0.2, 0.9, 0.5)),
}

# White reference (A4 paper, LED 100mA)
WREF = {'R': 3449, 'S': 938, 'T': 231, 'U': 165, 'V': 249, 'W': 193}

# DPF values for fingertip
DPF_680 = 3.0
DPF_860 = 2.5

# Frostbite warning thresholds (TOI_cal rises toward zero = danger)
TOI_CAL_WARNING = -0.15
TOI_CAL_DANGER  = -0.12

class I2CBus:
    def __init__(self, bus_num):
        self.fd = os.open(f"/dev/i2c-{bus_num}", os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, ADDR)

    def rb(self, reg):
        os.write(self.fd, bytes([reg]))
        return os.read(self.fd, 1)[0]

    def wb(self, reg, val):
        os.write(self.fd, bytes([reg, val]))

    def vr(self, reg):
        for _ in range(100):
            if (self.rb(0x00) & 0x02) == 0:
                break
            time.sleep(0.005)
        self.wb(0x01, reg)
        for _ in range(100):
            if (self.rb(0x00) & 0x01) != 0:
                break
            time.sleep(0.005)
        return self.rb(0x02)

    def vw(self, reg, val):
        for _ in range(100):
            if (self.rb(0x00) & 0x02) == 0:
                break
            time.sleep(0.005)
        self.wb(0x01, reg | 0x80)
        for _ in range(100):
            if (self.rb(0x00) & 0x02) == 0:
                break
            time.sleep(0.005)
        self.wb(0x01, val)

    def rcal(self, addr):
        b = [self.vr(addr + i) for i in range(4)]
        raw = (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]
        return struct.unpack('!f', struct.pack('!I', raw))[0]

    def close(self):
        os.close(self.fd)


class Dashboard(Gtk.Window):
    def __init__(self):
        super().__init__(title="AS7263 NIR Monitor")
        self.set_default_size(1280, 720)
        self.set_app_paintable(True)

        self.set_decorated(False)
        self.fullscreen()

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect('draw', self.on_draw)
        self.add(self.drawing_area)

        # Data
        self.channels = {k: 0.0 for k in CALS}
        self.temp = 0
        self.toi = 0.0
        self.toi_cal = 0.0
        self.sto2 = 0.0
        self.warning_level = "SAFE"
        self.toi_history = []
        self.toi_cal_history = []
        self.sto2_history = []
        self.temp_history = []
        self.ch_history = {k: [] for k in CALS}  # all 6 channels
        self.sample_count = 0
        self.connected = False
        self.error_msg = ""

        # Sensor thread
        self.running = True
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.sensor_loop, daemon=True)
        self.thread.start()

        # Refresh UI at 2 Hz
        GLib.timeout_add(500, self.refresh)
        self.connect('destroy', self.on_quit)

    def on_quit(self, *args):
        self.running = False
        Gtk.main_quit()

    def refresh(self):
        self.drawing_area.queue_draw()
        return True

    def sensor_loop(self):
        try:
            bus = I2CBus(2)
            hw = bus.vr(0x00)
            st = bus.vr(0x01)
            if st != 0x3F:
                with self.lock:
                    self.error_msg = f"Wrong sensor: 0x{st:02X}"
                return

            with self.lock:
                self.connected = True

            # Config
            bus.vw(0x07, 0x0B)  # LED ON 100mA
            bus.vw(0x04, (0x03 << 4) | (0x03 << 2))  # gain=64x, one-shot
            bus.vw(0x05, 50)  # integration=140ms

            while self.running:
                try:
                    cv = bus.vr(0x04)
                    bus.vw(0x04, (cv & 0xF3) | 0x0C)
                    time.sleep(0.35)

                    ch = {k: bus.rcal(v) for k, v in CALS.items()}
                    temp = bus.vr(0x06)
                    s, w = ch['S'], ch['W']
                    toi = (w - s) / (w + s) if (w + s) > 0 else 0

                    # White-reference calibrated TOI
                    sn = s / WREF['S']
                    wn = w / WREF['W']
                    toi_cal = (wn - sn) / (wn + sn) if (wn + sn) > 0 else 0

                    # DPF-corrected StO2 (fingertip)
                    a_s = abs(math.log(WREF['S'] / s)) / DPF_680 if s > 0 else 0
                    a_w = abs(math.log(WREF['W'] / w)) / DPF_860 if w > 0 else 0
                    sto2 = a_w / (a_w + a_s) if (a_w + a_s) > 0 else 0

                    # Three-level warning
                    if toi_cal > TOI_CAL_DANGER:
                        wlevel = "DANGER"
                    elif toi_cal > TOI_CAL_WARNING:
                        wlevel = "WARNING"
                    else:
                        wlevel = "SAFE"

                    with self.lock:
                        self.channels = ch
                        self.temp = temp
                        self.toi = toi
                        self.toi_cal = toi_cal
                        self.sto2 = sto2
                        self.warning_level = wlevel
                        self.sample_count += 1
                        self.toi_history.append(toi)
                        self.toi_cal_history.append(toi_cal)
                        self.sto2_history.append(sto2)
                        self.temp_history.append(temp)
                        for k in CALS:
                            self.ch_history[k].append(ch[k])
                        if len(self.toi_history) > 600:
                            self.toi_history.pop(0)
                            self.toi_cal_history.pop(0)
                            self.sto2_history.pop(0)
                            self.temp_history.pop(0)
                            for k in CALS:
                                self.ch_history[k].pop(0)
                        self.error_msg = ""

                except OSError:
                    with self.lock:
                        self.error_msg = "I2C error - check wires"
                    time.sleep(1)

                time.sleep(1.65)  # ~2s total cycle

            bus.vw(0x07, 0x00)  # LED off
            bus.close()
        except Exception as e:
            with self.lock:
                self.error_msg = str(e)

    def on_draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()

        with self.lock:
            ch = dict(self.channels)
            temp = self.temp
            toi = self.toi
            toi_cal = self.toi_cal
            sto2 = self.sto2
            wlevel = self.warning_level
            history = list(self.toi_history)
            toi_cal_hist = list(self.toi_cal_history)
            sto2_hist = list(self.sto2_history)
            temp_hist = list(self.temp_history)
            ch_hist = {k: list(v) for k, v in self.ch_history.items()}
            count = self.sample_count
            connected = self.connected
            err = self.error_msg

        # Background
        cr.set_source_rgb(0.08, 0.08, 0.12)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        # Title
        cr.select_font_face("Liberation Sans", 0, 1)
        cr.set_font_size(28)
        cr.set_source_rgb(0.0, 0.83, 1.0)
        cr.move_to(20, 40)
        cr.show_text("AS7263 NIR Tissue Monitor")

        cr.set_font_size(14)
        cr.set_source_rgb(0.5, 0.5, 0.6)
        cr.move_to(20, 60)
        cr.show_text(f"i.MX8MP EVK  |  I2C3 (J21)  |  LED 100mA  |  Gain 64x  |  Sample #{count}")

        if err:
            cr.set_font_size(20)
            cr.set_source_rgb(1.0, 0.3, 0.3)
            cr.move_to(20, 90)
            cr.show_text(f"ERROR: {err}")

        if not connected and not err:
            cr.set_font_size(20)
            cr.set_source_rgb(1.0, 1.0, 0.3)
            cr.move_to(20, 90)
            cr.show_text("Connecting to sensor...")
            return

        # --- Left panel: channel bars ---
        panel_x = 20
        panel_y = 80
        bar_w = 200
        bar_h = 28
        gap = 8

        cr.set_font_size(16)
        cr.set_source_rgb(0.7, 0.7, 0.8)
        cr.move_to(panel_x, panel_y + 15)
        cr.show_text("Spectral Channels (uW/cm2)")

        max_val = max(ch.values()) if max(ch.values()) > 0 else 1
        for i, key in enumerate(['R', 'S', 'T', 'U', 'V', 'W']):
            y = panel_y + 30 + i * (bar_h + gap)
            label, color = LABELS[key]
            val = ch[key]
            fill = min(val / max_val, 1.0) * bar_w

            # Bar background
            cr.set_source_rgb(0.15, 0.15, 0.2)
            cr.rectangle(panel_x + 90, y, bar_w, bar_h)
            cr.fill()

            # Bar fill
            cr.set_source_rgb(*color)
            cr.rectangle(panel_x + 90, y, fill, bar_h)
            cr.fill()

            # Label
            cr.set_font_size(15)
            cr.set_source_rgb(*color)
            cr.move_to(panel_x, y + 20)
            cr.show_text(f"{key} {label}")

            # Value
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(panel_x + 300, y + 20)
            cr.show_text(f"{val:.0f}")

        # --- Center panel: StO2 + Warning + Temperature ---
        cx = 400
        cy = 80

        # Warning banner
        cr.set_font_size(16)
        cr.set_source_rgb(0.7, 0.7, 0.8)
        cr.move_to(cx, cy + 15)
        cr.show_text("Frostbite Risk")
        cr.set_font_size(42)
        if wlevel == "DANGER":
            cr.set_source_rgb(1.0, 0.2, 0.2)
        elif wlevel == "WARNING":
            cr.set_source_rgb(1.0, 0.8, 0.2)
        else:
            cr.set_source_rgb(0.2, 1.0, 0.4)
        cr.move_to(cx, cy + 60)
        cr.show_text(wlevel)

        # StO2 (DPF-corrected)
        cr.set_font_size(16)
        cr.set_source_rgb(0.7, 0.7, 0.8)
        cr.move_to(cx, cy + 90)
        cr.show_text("Tissue O2 Saturation (StO2, fingertip DPF)")
        cr.set_font_size(48)
        if wlevel == "DANGER":
            cr.set_source_rgb(1.0, 0.2, 0.2)
        elif wlevel == "WARNING":
            cr.set_source_rgb(1.0, 0.8, 0.2)
        else:
            cr.set_source_rgb(0.2, 1.0, 0.4)
        cr.move_to(cx, cy + 145)
        cr.show_text(f"{sto2:.1%}")

        # Temperature + TOI details
        cr.set_font_size(16)
        cr.set_source_rgb(0.7, 0.7, 0.8)
        cr.move_to(cx, cy + 175)
        cr.show_text("Details")
        cr.set_font_size(20)
        cr.set_source_rgb(1.0, 0.5, 0.2) if temp > 35 else cr.set_source_rgb(0.3, 0.8, 1.0)
        cr.move_to(cx, cy + 200)
        cr.show_text(f"Temp: {temp} C")
        cr.set_font_size(15)
        cr.set_source_rgb(0.5, 0.5, 0.6)
        cr.move_to(cx, cy + 222)
        cr.show_text(f"TOI_raw: {toi:.4f}  |  TOI_cal: {toi_cal:.4f}  |  baseline: -0.210")

        # --- Helper: draw a multi-line chart ---
        def draw_chart(cx, cy, cw, ch_h, title, series, y_fmt=".3f"):
            """series: list of (label, color_rgb, data_list)"""
            cr.set_source_rgb(0.1, 0.1, 0.15)
            cr.rectangle(cx, cy, cw, ch_h)
            cr.fill()
            cr.set_source_rgb(0.3, 0.3, 0.4)
            cr.set_line_width(1)
            cr.rectangle(cx, cy, cw, ch_h)
            cr.stroke()
            cr.set_font_size(14)
            cr.set_source_rgb(0.7, 0.7, 0.8)
            cr.move_to(cx + 10, cy + 18)
            cr.show_text(title)

            all_vals = []
            for _, _, data in series:
                all_vals.extend(data)
            if len(all_vals) < 2:
                return

            v_min = min(all_vals)
            v_max = max(all_vals)
            margin_v = (v_max - v_min) * 0.25 + 0.01
            v_min -= margin_v
            v_max += margin_v

            margin = 60
            px = cx + margin
            pw = cw - margin - 10
            py = cy + 30
            ph = ch_h - 50

            # Grid
            cr.set_line_width(0.5)
            for j in range(5):
                gy = py + ph * j / 4
                cr.set_source_rgb(0.2, 0.2, 0.25)
                cr.move_to(px, gy)
                cr.line_to(px + pw, gy)
                cr.stroke()
                val = v_max - (v_max - v_min) * j / 4
                cr.set_font_size(10)
                cr.set_source_rgb(0.5, 0.5, 0.6)
                cr.move_to(cx + 3, gy + 4)
                cr.show_text(f"{val:{y_fmt}}")

            # Lines
            for label, color, data in series:
                if len(data) < 2:
                    continue
                cr.set_source_rgb(*color)
                cr.set_line_width(2)
                for i, val in enumerate(data):
                    x = px + (i / max(len(data) - 1, 1)) * pw
                    y = py + (1 - (val - v_min) / (v_max - v_min)) * ph
                    if i == 0:
                        cr.move_to(x, y)
                    else:
                        cr.line_to(x, y)
                cr.stroke()

            # Legend
            cr.set_font_size(11)
            lx = px + 5
            for i, (label, color, _) in enumerate(series):
                cr.set_source_rgb(*color)
                cr.move_to(lx + i * 100, py + ph + 15)
                cr.show_text(f"- {label}")

        # --- Bottom panel: two charts side by side ---
        chart_y = 310
        chart_h = h - 330
        half_w = (w - 50) // 2

        # Left chart: TOI + Temperature
        toi_series = [("TOI", (0.0, 1.0, 0.5), history)]
        if temp_hist:
            # Normalize temp to TOI scale for overlay
            toi_series.append(("Temp", (1.0, 0.4, 0.2), temp_hist))

        # Draw StO2 + TOI_cal chart
        sto2_series = []
        if sto2_hist:
            sto2_series.append(("StO2", (0.0, 1.0, 0.5), sto2_hist))
        draw_chart(20, chart_y, half_w, chart_h,
                   "StO2 Trend — DPF corrected (last 20 min)",
                   sto2_series if sto2_series else [("TOI_cal", (0.0, 1.0, 0.5), toi_cal_hist)],
                   y_fmt=".3f")

        # Right chart: Key spectral channels
        spec_series = []
        for key in ['S', 'W', 'V', 'R']:
            if ch_hist.get(key):
                label, color = LABELS[key]
                spec_series.append((f"{key} {label}", color, ch_hist[key]))

        draw_chart(30 + half_w, chart_y, half_w, chart_h,
                   "Spectral Channels (uW/cm2)",
                   spec_series,
                   y_fmt=".0f")


def main():
    os.environ.setdefault('XDG_RUNTIME_DIR', '/run/user/0')
    win = Dashboard()
    win.show_all()
    Gtk.main()

if __name__ == '__main__':
    main()
