#!/usr/bin/env python3
"""
AS7263 NIR Multi-Function Dashboard (GTK3 + Cairo)

Features:
- DPF-corrected StO2 with frostbite warning zones
- White reference calibration built-in
- Baseline tracking with delta display
- Dual trend chart: StO2 + Temperature
- NDVI plant health mode
- All measurements on fingertip (DPF 3.0/2.5)

Usage: python3 as7263_dashboard.py
"""

import os
import sys
import time
import math
import struct
import fcntl
import threading
import cairo
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import subprocess
subprocess.run(["killall", "-9", "as7263_dashboard"], stderr=subprocess.DEVNULL)
subprocess.run(["killall", "-9", "as7263_display"], stderr=subprocess.DEVNULL)
subprocess.run(["killall", "-9", "as7263_countdown"], stderr=subprocess.DEVNULL)

# --- Config ---
I2C_SLAVE = 0x0703
ADDR = 0x49
CALS = {'R': 0x14, 'S': 0x18, 'T': 0x1C, 'U': 0x20, 'V': 0x24, 'W': 0x28}
CH_ORDER = ['R', 'S', 'T', 'U', 'V', 'W']
CH_NM = {'R': 610, 'S': 680, 'T': 730, 'U': 760, 'V': 810, 'W': 860}
CH_COLOR = {
    'R': (1.0, 0.3, 0.3), 'S': (1.0, 0.5, 0.2), 'T': (0.8, 0.2, 0.2),
    'U': (0.6, 0.3, 0.8), 'V': (0.3, 0.7, 1.0), 'W': (0.2, 0.9, 0.5),
}

# Fingertip DPF (Scholkmann & Wolf 2013, adapted)
DPF_680 = 3.0
DPF_860 = 2.5

# Default white reference (can be recalibrated)
WHITE_REF = {'R': 3449, 'S': 938, 'T': 231, 'U': 165, 'V': 249, 'W': 193}


class I2CBus:
    def __init__(self):
        self.fd = os.open("/dev/i2c-2", os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, ADDR)

    def rb(self, r):
        os.write(self.fd, bytes([r]))
        return os.read(self.fd, 1)[0]

    def wb(self, r, v):
        os.write(self.fd, bytes([r, v]))

    def vr(self, r):
        for _ in range(100):
            if (self.rb(0x00) & 0x02) == 0: break
            time.sleep(0.005)
        self.wb(0x01, r)
        for _ in range(100):
            if (self.rb(0x00) & 0x01) != 0: break
            time.sleep(0.005)
        return self.rb(0x02)

    def vw(self, r, v):
        for _ in range(100):
            if (self.rb(0x00) & 0x02) == 0: break
            time.sleep(0.005)
        self.wb(0x01, r | 0x80)
        for _ in range(100):
            if (self.rb(0x00) & 0x02) == 0: break
            time.sleep(0.005)
        self.wb(0x01, v)

    def rcal(self, a):
        b = [self.vr(a + i) for i in range(4)]
        raw = (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]
        return struct.unpack('!f', struct.pack('!I', raw))[0]

    def close(self):
        os.close(self.fd)


def calc_sto2(ch, wref):
    """DPF-corrected StO2 from raw channels + white reference."""
    s, w = ch.get('S', 0), ch.get('W', 0)
    ws, ww = wref['S'], wref['W']
    if s <= 0 or w <= 0 or ws <= 0 or ww <= 0:
        return 0.0
    a_s = abs(math.log(ws / s)) / DPF_680
    a_w = abs(math.log(ww / w)) / DPF_860
    return a_w / (a_w + a_s) if (a_w + a_s) > 0 else 0.0


def calc_toi_cal(ch, wref):
    """White-reference calibrated TOI."""
    s_n = ch.get('S', 0) / wref['S'] if wref['S'] > 0 else 0
    w_n = ch.get('W', 0) / wref['W'] if wref['W'] > 0 else 0
    return (w_n - s_n) / (w_n + s_n) if (w_n + s_n) > 0 else 0


def calc_ndvi(ch, wref):
    """NDVI = (V_810 - S_680) / (V_810 + S_680), normalized."""
    s_n = ch.get('S', 0) / wref['S'] if wref['S'] > 0 else 0
    v_n = ch.get('V', 0) / wref['V'] if wref['V'] > 0 else 0
    return (v_n - s_n) / (v_n + s_n) if (v_n + s_n) > 0 else 0


class Dashboard(Gtk.Window):
    MAX_HIST = 300

    def __init__(self):
        super().__init__(title="AS7263 Dashboard")
        self.set_decorated(False)
        self.fullscreen()
        self.set_app_paintable(True)

        self.da = Gtk.DrawingArea()
        self.da.connect('draw', self.on_draw)
        self.add(self.da)

        # State
        self.ch = {k: 0.0 for k in CALS}
        self.temp = 0
        self.sto2 = 0.0
        self.toi_cal = 0.0
        self.ndvi = 0.0
        self.baseline_sto2 = None
        self.sto2_hist = []
        self.temp_hist = []
        self.toi_hist = []
        self.sample_n = 0
        self.connected = False
        self.measuring = False  # standby until user clicks
        self.error = ""
        self.wref = dict(WHITE_REF)
        self.lock = threading.Lock()
        self.running = True

        self.thread = threading.Thread(target=self.sensor_loop, daemon=True)
        self.thread.start()

        GLib.timeout_add(400, self.refresh)
        GLib.timeout_add(5000, self._auto_screenshot)  # screenshot after 5s
        self.connect('destroy', self.on_quit)
        self.connect('button-press-event', self.on_click)
        self.add_events(1 << 8)  # GDK_BUTTON_PRESS_MASK

    def _auto_screenshot(self):
        self._save_screenshot()
        return True  # keep running every 5s

    def on_click(self, widget, event):
        with self.lock:
            self.measuring = not self.measuring

    def on_quit(self, *args):
        self.running = False
        Gtk.main_quit()

    def refresh(self):
        self.da.queue_draw()
        return self.running

    def _save_screenshot(self):
        try:
            w = self.da.get_allocated_width()
            h = self.da.get_allocated_height()
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            cr = cairo.Context(surface)
            self.on_draw(self.da, cr)
            surface.write_to_png("/tmp/dashboard_screenshot.png")
        except Exception:
            pass

    def sensor_loop(self):
        try:
            bus = I2CBus()
            st = bus.vr(0x01)
            if st != 0x3F:
                with self.lock:
                    self.error = f"Wrong sensor: 0x{st:02X}"
                return
            with self.lock:
                self.connected = True

            bus.vw(0x07, 0x00)  # LED off by default
            bus.vw(0x04, (0x03 << 4) | (0x03 << 2))
            bus.vw(0x05, 50)
            led_on = False

            while self.running:
                with self.lock:
                    want_measure = self.measuring

                if not want_measure:
                    if led_on:
                        bus.vw(0x07, 0x00)
                        led_on = False
                    time.sleep(0.5)
                    continue

                try:
                    if not led_on:
                        bus.vw(0x07, 0x0B)  # LED on
                        led_on = True
                        time.sleep(0.2)
                    cv = bus.vr(0x04)
                    bus.vw(0x04, (cv & 0xF3) | 0x0C)
                    time.sleep(0.35)
                    ch = {k: bus.rcal(v) for k, v in CALS.items()}
                    temp = bus.vr(0x06)

                    sto2 = calc_sto2(ch, self.wref)
                    toi_cal = calc_toi_cal(ch, self.wref)
                    ndvi = calc_ndvi(ch, self.wref)

                    with self.lock:
                        self.ch = ch
                        self.temp = temp
                        self.sto2 = sto2
                        self.toi_cal = toi_cal
                        self.ndvi = ndvi
                        self.sample_n += 1
                        self.sto2_hist.append(sto2)
                        self.temp_hist.append(temp)
                        self.toi_hist.append(toi_cal)
                        if len(self.sto2_hist) > self.MAX_HIST:
                            self.sto2_hist.pop(0)
                            self.temp_hist.pop(0)
                            self.toi_hist.pop(0)
                        if self.baseline_sto2 is None and self.sample_n == 10:
                            self.baseline_sto2 = sum(self.sto2_hist[-5:]) / 5
                        self.error = ""
                except OSError:
                    with self.lock:
                        self.error = "I2C error"
                    time.sleep(1)
                time.sleep(1.65)

            bus.vw(0x07, 0x00)
            bus.close()
        except Exception as e:
            with self.lock:
                self.error = str(e)

    def on_draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()

        with self.lock:
            ch = dict(self.ch)
            temp = self.temp
            sto2 = self.sto2
            toi_cal = self.toi_cal
            ndvi = self.ndvi
            baseline = self.baseline_sto2
            sto2_h = list(self.sto2_hist)
            temp_h = list(self.temp_hist)
            toi_h = list(self.toi_hist)
            sn = self.sample_n
            conn = self.connected
            err = self.error

        # Background
        cr.set_source_rgb(0.05, 0.05, 0.09)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        cr.select_font_face("Liberation Sans", 0, 1)

        # Title bar
        cr.set_font_size(22)
        cr.set_source_rgb(0.0, 0.83, 1.0)
        cr.move_to(15, 30)
        cr.show_text("AS7263 NIR Tissue Monitor")
        cr.set_font_size(12)
        cr.set_source_rgb(0.4, 0.4, 0.5)
        cr.move_to(15, 48)
        cr.show_text(f"i.MX8MP EVK | I2C3 (J21) | Fingertip | LED 100mA | DPF 3.0/2.5 | #{sn}")

        if err:
            cr.set_font_size(16)
            cr.set_source_rgb(1, 0.3, 0.3)
            cr.move_to(w - 300, 30)
            cr.show_text(f"ERR: {err}")

        if not conn and not err:
            cr.set_font_size(28)
            cr.set_source_rgb(1, 1, 0.3)
            cr.move_to(w // 2 - 100, h // 2)
            cr.show_text("Connecting...")
            return

        with self.lock:
            is_measuring = self.measuring

        # Standby / measuring indicator
        if is_measuring:
            cr.set_source_rgb(0.1, 0.8, 0.3)
            cr.set_font_size(14)
            cr.move_to(w - 220, 30)
            cr.show_text("MEASURING  (click to stop)")
        else:
            cr.set_source_rgb(0.6, 0.6, 0.2)
            cr.set_font_size(14)
            cr.move_to(w - 220, 30)
            cr.show_text("STANDBY  (click to start)")

        # ===== LEFT COLUMN (0 ~ 320px) =====
        lx = 15

        # -- StO2 gauge --
        cr.set_font_size(13)
        cr.set_source_rgb(0.5, 0.5, 0.6)
        cr.move_to(lx, 75)
        cr.show_text("StO2 (DPF-corrected)")

        cr.set_font_size(64)
        pct = sto2 * 100
        if pct > 35:
            cr.set_source_rgb(0.1, 1.0, 0.4)
        elif pct > 25:
            cr.set_source_rgb(1.0, 0.8, 0.2)
        else:
            cr.set_source_rgb(1.0, 0.2, 0.2)
        cr.move_to(lx, 145)
        cr.show_text(f"{pct:.1f}%")

        # Delta from baseline
        if baseline is not None:
            delta = (sto2 - baseline) * 100
            cr.set_font_size(18)
            if delta >= 0:
                cr.set_source_rgb(0.3, 1.0, 0.5)
                cr.move_to(lx + 220, 130)
                cr.show_text(f"+{delta:.1f}")
            else:
                cr.set_source_rgb(1.0, 0.4, 0.3)
                cr.move_to(lx + 220, 130)
                cr.show_text(f"{delta:.1f}")
            cr.set_font_size(10)
            cr.set_source_rgb(0.4, 0.4, 0.5)
            cr.move_to(lx + 220, 145)
            cr.show_text(f"vs baseline {baseline*100:.1f}%")

        # Warning zone bar
        bar_x, bar_y, bar_w, bar_h = lx, 155, 440, 20
        # Green zone (>35%)
        cr.set_source_rgb(0.1, 0.5, 0.2)
        cr.rectangle(bar_x + bar_w * 0.35, bar_y, bar_w * 0.65, bar_h)
        cr.fill()
        # Yellow zone (25-35%)
        cr.set_source_rgb(0.6, 0.5, 0.1)
        cr.rectangle(bar_x + bar_w * 0.25, bar_y, bar_w * 0.10, bar_h)
        cr.fill()
        # Red zone (<25%)
        cr.set_source_rgb(0.5, 0.1, 0.1)
        cr.rectangle(bar_x, bar_y, bar_w * 0.25, bar_h)
        cr.fill()
        # Marker — large arrow
        mx = bar_x + min(max(sto2, 0), 1.0) * bar_w
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(mx, bar_y - 2)
        cr.line_to(mx - 12, bar_y - 20)
        cr.line_to(mx + 12, bar_y - 20)
        cr.fill()
        # Arrow outline
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(2)
        cr.move_to(mx, bar_y - 2)
        cr.line_to(mx - 12, bar_y - 20)
        cr.line_to(mx + 12, bar_y - 20)
        cr.close_path()
        cr.stroke()
        # Labels
        cr.set_font_size(9)
        cr.set_source_rgb(0.6, 0.6, 0.7)
        cr.move_to(bar_x, bar_y + bar_h + 10)
        cr.show_text("0%")
        cr.move_to(bar_x + bar_w * 0.23, bar_y + bar_h + 10)
        cr.show_text("25%")
        cr.move_to(bar_x + bar_w * 0.5, bar_y + bar_h + 10)
        cr.show_text("SAFE")
        cr.move_to(bar_x + bar_w - 25, bar_y + bar_h + 10)
        cr.show_text("100%")
        cr.set_source_rgb(1.0, 0.3, 0.3)
        cr.move_to(bar_x + bar_w * 0.05, bar_y + bar_h + 10)
        cr.show_text("DANGER")

        # -- Temperature --
        cr.set_font_size(13)
        cr.set_source_rgb(0.5, 0.5, 0.6)
        cr.move_to(lx, 200)
        cr.show_text("Temperature")
        cr.set_font_size(42)
        cr.set_source_rgb(1.0, 0.5, 0.2) if temp > 35 else cr.set_source_rgb(0.3, 0.8, 1.0)
        cr.move_to(lx, 245)
        cr.show_text(f"{temp} C")

        # -- TOI_cal --
        cr.set_font_size(13)
        cr.set_source_rgb(0.5, 0.5, 0.6)
        cr.move_to(lx + 160, 200)
        cr.show_text("TOI (white-ref)")
        cr.set_font_size(30)
        cr.set_source_rgb(0.7, 0.7, 0.8)
        cr.move_to(lx + 160, 240)
        cr.show_text(f"{toi_cal:.4f}")

        # -- NDVI --
        cr.set_font_size(13)
        cr.set_source_rgb(0.5, 0.5, 0.6)
        cr.move_to(lx, 275)
        cr.show_text("NDVI (plant health)")
        cr.set_font_size(30)
        if ndvi > 0.2:
            cr.set_source_rgb(0.2, 0.9, 0.3)
        else:
            cr.set_source_rgb(0.7, 0.7, 0.8)
        cr.move_to(lx, 310)
        cr.show_text(f"{ndvi:.3f}")

        # -- Channel bars --
        cr.set_font_size(11)
        cr.set_source_rgb(0.5, 0.5, 0.6)
        cr.move_to(lx, 340)
        cr.show_text("Spectral Channels (uW/cm2)")

        if ch:
            max_v = max(ch.values()) if max(ch.values()) > 0 else 1
            for i, k in enumerate(CH_ORDER):
                y = 350 + i * 24
                val = ch.get(k, 0)
                cr.set_source_rgb(0.12, 0.12, 0.17)
                cr.rectangle(lx + 65, y, 300, 18)
                cr.fill()
                cr.set_source_rgb(*CH_COLOR[k])
                fill = min(val / max_v, 1.0) * 300
                cr.rectangle(lx + 65, y, fill, 18)
                cr.fill()
                cr.set_font_size(11)
                cr.set_source_rgb(*CH_COLOR[k])
                cr.move_to(lx, y + 13)
                cr.show_text(f"{k} {CH_NM[k]}")
                cr.set_source_rgb(0.9, 0.9, 0.9)
                cr.move_to(lx + 375, y + 13)
                cr.show_text(f"{val:.0f}")

        # ===== RIGHT AREA: Charts =====
        cx = 480
        cw = w - cx - 15

        # -- Top chart: StO2 trend --
        self._draw_trend(cr, cx, 60, cw, (h - 80) // 2 - 10,
                         "StO2 % (DPF-corrected fingertip)",
                         [("StO2", (0.1, 1.0, 0.4), [v * 100 for v in sto2_h])],
                         baseline_val=baseline * 100 if baseline else None,
                         baseline_label="baseline",
                         y_fmt=".1f",
                         warn_below=25)

        # -- Bottom chart: TOI_cal + Temperature --
        cy2 = 60 + (h - 80) // 2 + 5
        ch2 = (h - 80) // 2 - 15
        self._draw_trend(cr, cx, cy2, cw, ch2,
                         "TOI_cal + Temperature",
                         [
                             ("TOI_cal", (0.0, 1.0, 0.5), [v for v in toi_h]),
                             ("Temp", (1.0, 0.4, 0.2), [float(v) for v in temp_h]),
                         ],
                         y_fmt=".2f")

    def _draw_trend(self, cr, cx, cy, cw, ch, title, series, baseline_val=None, baseline_label="", y_fmt=".1f", warn_below=None):
        # Background
        cr.set_source_rgb(0.08, 0.08, 0.13)
        cr.rectangle(cx, cy, cw, ch)
        cr.fill()
        cr.set_source_rgb(0.25, 0.25, 0.35)
        cr.set_line_width(1)
        cr.rectangle(cx, cy, cw, ch)
        cr.stroke()

        cr.set_font_size(12)
        cr.set_source_rgb(0.6, 0.6, 0.7)
        cr.move_to(cx + 8, cy + 16)
        cr.show_text(title)

        all_v = []
        for _, _, data in series:
            all_v.extend(data)
        if len(all_v) < 2:
            return

        v_min, v_max = min(all_v), max(all_v)
        if baseline_val is not None:
            v_min = min(v_min, baseline_val)
            v_max = max(v_max, baseline_val)
        margin = (v_max - v_min) * 0.2 + 0.1
        v_min -= margin
        v_max += margin

        mg = 50
        px, pw = cx + mg, cw - mg - 10
        py, ph = cy + 25, ch - 42

        # Grid
        cr.set_line_width(0.5)
        for j in range(5):
            gy = py + ph * j / 4
            cr.set_source_rgb(0.15, 0.15, 0.22)
            cr.move_to(px, gy)
            cr.line_to(px + pw, gy)
            cr.stroke()
            val = v_max - (v_max - v_min) * j / 4
            cr.set_font_size(9)
            cr.set_source_rgb(0.45, 0.45, 0.55)
            cr.move_to(cx + 2, gy + 3)
            cr.show_text(f"{val:{y_fmt}}")

        # Warning zone
        if warn_below is not None and v_min < warn_below < v_max:
            wy = py + (1 - (warn_below - v_min) / (v_max - v_min)) * ph
            cr.set_source_rgba(1.0, 0.15, 0.1, 0.08)
            cr.rectangle(px, wy, pw, py + ph - wy)
            cr.fill()
            cr.set_source_rgba(1.0, 0.3, 0.2, 0.5)
            cr.set_line_width(1)
            cr.set_dash([6, 4])
            cr.move_to(px, wy)
            cr.line_to(px + pw, wy)
            cr.stroke()
            cr.set_dash([])
            cr.set_font_size(9)
            cr.move_to(px + 2, wy - 3)
            cr.show_text("DANGER")

        # Baseline
        if baseline_val is not None:
            by = py + (1 - (baseline_val - v_min) / (v_max - v_min)) * ph
            cr.set_source_rgba(0.3, 0.6, 1.0, 0.5)
            cr.set_line_width(1)
            cr.set_dash([5, 3])
            cr.move_to(px, by)
            cr.line_to(px + pw, by)
            cr.stroke()
            cr.set_dash([])
            cr.set_font_size(9)
            cr.set_source_rgb(0.3, 0.6, 1.0)
            cr.move_to(px + pw - 80, by - 3)
            cr.show_text(f"{baseline_label} {baseline_val:{y_fmt}}")

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
        cr.set_font_size(10)
        for i, (label, color, _) in enumerate(series):
            cr.set_source_rgb(*color)
            cr.move_to(px + pw - 180 + i * 90, py + 12)
            cr.show_text(f"-- {label}")


def main():
    os.environ.setdefault('XDG_RUNTIME_DIR', '/run/user/0')
    win = Dashboard()
    win.show_all()
    Gtk.main()


if __name__ == '__main__':
    main()
