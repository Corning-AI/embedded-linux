#!/usr/bin/env python3
"""
AS7263 Countdown-Triggered Measurement

Shows a fullscreen countdown on HDMI, then starts LED + data collection
at exactly t=0. Eliminates the delay between hand placement and measurement.

Usage: python3 as7263_countdown.py [countdown_seconds] [num_samples]
  Default: 10s countdown, 30 samples
"""

import os
import sys
import time
import math
import struct
import fcntl
import signal
import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

# Kill any previous instance to prevent dual-window overlap
# (overlapping countdowns cause confusing display: 10,9,8,7,10,9,8...)
subprocess.run(["killall", "-9", "as7263_countdown"], stderr=subprocess.DEVNULL)
subprocess.run(["killall", "-9", "as7263_display"], stderr=subprocess.DEVNULL)

# --- Config ---
COUNTDOWN = int(sys.argv[1]) if len(sys.argv) > 1 else 10
NUM_SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 30
I2C_SLAVE = 0x0703
ADDR = 0x49
CALS = {'R': 0x14, 'S': 0x18, 'T': 0x1C, 'U': 0x20, 'V': 0x24, 'W': 0x28}
WREF = {'R': 3449, 'S': 938, 'T': 231, 'U': 165, 'V': 249, 'W': 193}

# DPF values for fingertip
DPF_680 = 3.0
DPF_860 = 2.5

# Frostbite warning thresholds (TOI_cal rises toward zero = danger)
TOI_CAL_WARNING = -0.15
TOI_CAL_DANGER  = -0.12

LABELS = {
    'R': ('610nm', (1.0, 0.3, 0.3)),
    'S': ('680nm', (1.0, 0.5, 0.2)),
    'T': ('730nm', (0.9, 0.2, 0.2)),
    'U': ('760nm', (0.6, 0.3, 0.8)),
    'V': ('810nm', (0.3, 0.7, 1.0)),
    'W': ('860nm', (0.2, 0.9, 0.5)),
}


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


class CountdownApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="AS7263 Measurement")
        self.set_decorated(False)
        self.fullscreen()
        self.set_app_paintable(True)

        self.da = Gtk.DrawingArea()
        self.da.connect('draw', self.on_draw)
        self.add(self.da)

        # State
        self.phase = 'countdown'  # countdown -> measuring -> done
        self.countdown_val = COUNTDOWN
        self.samples = []
        self.current = {}
        self.temp = 0
        self.toi_raw = 0
        self.toi_cal = 0
        self.sto2 = 0
        self.warning_level = "SAFE"
        self.sample_num = 0
        self.error = ""
        self.lock = threading.Lock()
        self.running = True

        # Start countdown timer
        GLib.timeout_add(100, self.refresh)
        GLib.timeout_add(1000, self.tick_countdown)
        self.connect('destroy', self.on_quit)

    def on_quit(self, *args):
        self.running = False
        Gtk.main_quit()

    def refresh(self):
        self.da.queue_draw()
        return self.running

    def tick_countdown(self):
        if self.phase != 'countdown':
            return False
        self.countdown_val -= 1
        if self.countdown_val <= 0:
            self.phase = 'measuring'
            t = threading.Thread(target=self.measure_loop, daemon=True)
            t.start()
            return False
        return True

    def measure_loop(self):
        try:
            bus = I2CBus()
            # Config + LED ON at exactly t=0
            bus.vw(0x07, 0x0B)  # LED 100mA
            bus.vw(0x04, (0x03 << 4) | (0x03 << 2))
            bus.vw(0x05, 50)

            for n in range(1, NUM_SAMPLES + 1):
                if not self.running:
                    break
                try:
                    cv = bus.vr(0x04)
                    bus.vw(0x04, (cv & 0xF3) | 0x0C)
                    time.sleep(0.35)
                    ch = {k: bus.rcal(v) for k, v in CALS.items()}
                    temp = bus.vr(0x06)
                    s, w = ch['S'], ch['W']
                    toi_raw = (w - s) / (w + s) if (w + s) > 0 else 0
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
                        self.current = ch
                        self.temp = temp
                        self.toi_raw = toi_raw
                        self.toi_cal = toi_cal
                        self.sto2 = sto2
                        self.warning_level = wlevel
                        self.sample_num = n
                        self.samples.append((n, temp, toi_raw, toi_cal, sto2, ch['S'], ch['W']))
                        self.error = ""

                    print(f"{n},{ch['R']:.0f},{ch['S']:.0f},{ch['T']:.0f},"
                          f"{ch['U']:.0f},{ch['V']:.0f},{ch['W']:.0f},"
                          f"{temp},{toi_raw:.4f},{toi_cal:.4f},{sto2:.3f},{wlevel}")

                except OSError as e:
                    with self.lock:
                        self.error = str(e)
                time.sleep(1.65)

            bus.vw(0x07, 0x00)
            bus.close()
        except Exception as e:
            with self.lock:
                self.error = str(e)

        with self.lock:
            self.phase = 'done'

    def on_draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()

        # Background
        cr.set_source_rgb(0.06, 0.06, 0.10)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        with self.lock:
            phase = self.phase
            cd = self.countdown_val
            samples = list(self.samples)
            ch = dict(self.current)
            temp = self.temp
            toi_cal = self.toi_cal
            toi_raw = self.toi_raw
            sto2 = self.sto2
            wlevel = self.warning_level
            sn = self.sample_num
            err = self.error

        if phase == 'countdown':
            self._draw_countdown(cr, w, h, cd)
        elif phase == 'measuring':
            self._draw_live(cr, w, h, samples, ch, temp, toi_cal, toi_raw, sto2, wlevel, sn, err)
        else:
            self._draw_live(cr, w, h, samples, ch, temp, toi_cal, toi_raw, sto2, wlevel, sn, err)
            cr.set_font_size(32)
            cr.set_source_rgb(0.2, 1.0, 0.4)
            cr.move_to(w // 2 - 150, h - 30)
            cr.show_text(f"DONE — {len(samples)} samples collected")

    def _draw_countdown(self, cr, w, h, cd):
        # Big countdown number
        cr.select_font_face("Liberation Sans", 0, 1)
        cr.set_font_size(240)
        cr.set_source_rgb(1.0, 0.8, 0.2)
        text = str(cd)
        ext = cr.text_extents(text)
        cr.move_to(w / 2 - ext.width / 2, h / 2 + ext.height / 2 - 40)
        cr.show_text(text)

        # Instructions
        cr.set_font_size(36)
        cr.set_source_rgb(0.7, 0.7, 0.8)
        msg = "Place cold hand on sensor NOW"
        ext = cr.text_extents(msg)
        cr.move_to(w / 2 - ext.width / 2, h / 2 + 100)
        cr.show_text(msg)

        cr.set_font_size(22)
        cr.set_source_rgb(0.5, 0.5, 0.6)
        msg2 = "LED turns on and measurement starts at 0"
        ext2 = cr.text_extents(msg2)
        cr.move_to(w / 2 - ext2.width / 2, h / 2 + 140)
        cr.show_text(msg2)

        # Title
        cr.set_font_size(28)
        cr.set_source_rgb(0.0, 0.83, 1.0)
        cr.move_to(20, 40)
        cr.show_text("AS7263 NIR Tissue Monitor — Countdown Mode")

    def _draw_live(self, cr, w, h, samples, ch, temp, toi_cal, toi_raw, sto2, wlevel, sn, err):
        cr.select_font_face("Liberation Sans", 0, 1)

        # Title bar
        cr.set_font_size(24)
        cr.set_source_rgb(0.0, 0.83, 1.0)
        cr.move_to(20, 35)
        cr.show_text(f"AS7263 NIR Tissue Monitor — Sample #{sn}/{NUM_SAMPLES}")

        if err:
            cr.set_source_rgb(1, 0.3, 0.3)
            cr.set_font_size(18)
            cr.move_to(20, 60)
            cr.show_text(f"I2C ERROR: {err}")

        # Left: Warning + StO2 + Temp
        cr.set_font_size(16)
        cr.set_source_rgb(0.6, 0.6, 0.7)
        cr.move_to(30, 75)
        cr.show_text("Frostbite Risk")
        cr.set_font_size(36)
        if wlevel == "DANGER":
            cr.set_source_rgb(1.0, 0.2, 0.2)
        elif wlevel == "WARNING":
            cr.set_source_rgb(1.0, 0.8, 0.2)
        else:
            cr.set_source_rgb(0.2, 1.0, 0.4)
        cr.move_to(30, 112)
        cr.show_text(wlevel)

        cr.set_font_size(16)
        cr.set_source_rgb(0.6, 0.6, 0.7)
        cr.move_to(30, 140)
        cr.show_text("StO2 (fingertip DPF)")
        cr.set_font_size(48)
        if wlevel == "DANGER":
            cr.set_source_rgb(1.0, 0.2, 0.2)
        elif wlevel == "WARNING":
            cr.set_source_rgb(1.0, 0.8, 0.2)
        else:
            cr.set_source_rgb(0.2, 1.0, 0.4)
        cr.move_to(30, 192)
        cr.show_text(f"{sto2:.1%}")

        cr.set_font_size(20)
        cr.set_source_rgb(1.0, 0.5, 0.2) if temp > 35 else cr.set_source_rgb(0.3, 0.8, 1.0)
        cr.move_to(30, 225)
        cr.show_text(f"Temp: {temp} C")

        cr.set_font_size(13)
        cr.set_source_rgb(0.4, 0.4, 0.5)
        cr.move_to(30, 248)
        cr.show_text(f"TOI_raw: {toi_raw:.4f}  |  TOI_cal: {toi_cal:.4f}  |  baseline: -0.210")

        # Channel bars
        cr.set_font_size(14)
        cr.set_source_rgb(0.6, 0.6, 0.7)
        cr.move_to(30, 290)
        cr.show_text("Spectral Channels (uW/cm2)")

        if ch:
            max_val = max(ch.values()) if max(ch.values()) > 0 else 1
            for i, key in enumerate(['R', 'S', 'T', 'U', 'V', 'W']):
                y = 305 + i * 30
                label, color = LABELS[key]
                val = ch.get(key, 0)
                fill = min(val / max_val, 1.0) * 160
                cr.set_source_rgb(0.15, 0.15, 0.2)
                cr.rectangle(90, y, 160, 22)
                cr.fill()
                cr.set_source_rgb(*color)
                cr.rectangle(90, y, fill, 22)
                cr.fill()
                cr.set_font_size(13)
                cr.set_source_rgb(*color)
                cr.move_to(10, y + 16)
                cr.show_text(f"{key} {label}")
                cr.set_source_rgb(1, 1, 1)
                cr.move_to(260, y + 16)
                cr.show_text(f"{val:.0f}")

        # Right: TOI trend chart
        chart_x = 350
        chart_y = 50
        chart_w = w - chart_x - 20
        chart_h = h - 80

        cr.set_source_rgb(0.1, 0.1, 0.15)
        cr.rectangle(chart_x, chart_y, chart_w, chart_h)
        cr.fill()
        cr.set_source_rgb(0.3, 0.3, 0.4)
        cr.set_line_width(1)
        cr.rectangle(chart_x, chart_y, chart_w, chart_h)
        cr.stroke()

        cr.set_font_size(14)
        cr.set_source_rgb(0.7, 0.7, 0.8)
        cr.move_to(chart_x + 10, chart_y + 20)
        cr.show_text("StO2 Trend — DPF corrected (real-time)")

        if len(samples) >= 2:
            sto2_vals = [s[4] for s in samples]
            v_min = min(sto2_vals) - 0.03
            v_max = max(sto2_vals) + 0.03
            # Ensure range covers baseline (~0.38) and danger zone (~0.43)
            v_min = min(v_min, 0.20)
            v_max = max(v_max, 0.50)

            margin = 55
            px = chart_x + margin
            pw = chart_w - margin - 15
            py = chart_y + 35
            ph = chart_h - 65

            # Grid
            cr.set_line_width(0.5)
            for j in range(5):
                gy = py + ph * j / 4
                cr.set_source_rgb(0.2, 0.2, 0.25)
                cr.move_to(px, gy)
                cr.line_to(px + pw, gy)
                cr.stroke()
                val = v_max - (v_max - v_min) * j / 4
                cr.set_font_size(11)
                cr.set_source_rgb(0.5, 0.5, 0.6)
                cr.move_to(chart_x + 3, gy + 4)
                cr.show_text(f"{val:.3f}")

            # Baseline line (StO2 = 0.38)
            bl_y = py + (1 - (0.38 - v_min) / (v_max - v_min)) * ph
            cr.set_source_rgba(0.3, 0.8, 1.0, 0.6)
            cr.set_line_width(1.5)
            cr.set_dash([8, 4])
            cr.move_to(px, bl_y)
            cr.line_to(px + pw, bl_y)
            cr.stroke()
            cr.set_font_size(11)
            cr.move_to(px + pw - 130, bl_y - 5)
            cr.show_text("baseline StO2=0.38")

            # Danger line (StO2 = 0.43)
            dl_y = py + (1 - (0.43 - v_min) / (v_max - v_min)) * ph
            cr.set_source_rgba(1.0, 0.2, 0.2, 0.6)
            cr.set_line_width(1.5)
            cr.set_dash([8, 4])
            cr.move_to(px, dl_y)
            cr.line_to(px + pw, dl_y)
            cr.stroke()
            cr.set_dash([])
            cr.set_font_size(11)
            cr.move_to(px + pw - 130, dl_y - 5)
            cr.show_text("DANGER StO2>0.43")

            # StO2 line
            cr.set_source_rgb(0.0, 1.0, 0.5)
            cr.set_line_width(2.5)
            for i, val in enumerate(sto2_vals):
                x = px + (i / max(len(sto2_vals) - 1, 1)) * pw
                y = py + (1 - (val - v_min) / (v_max - v_min)) * ph
                if i == 0:
                    cr.move_to(x, y)
                else:
                    cr.line_to(x, y)
            cr.stroke()

            # Dots with warning colors
            for i, val in enumerate(sto2_vals):
                x = px + (i / max(len(sto2_vals) - 1, 1)) * pw
                y = py + (1 - (val - v_min) / (v_max - v_min)) * ph
                if val > 0.43:
                    cr.set_source_rgb(1.0, 0.2, 0.2)
                elif val > 0.40:
                    cr.set_source_rgb(1.0, 0.8, 0.2)
                else:
                    cr.set_source_rgb(0.0, 1.0, 0.5)
                cr.arc(x, y, 3, 0, 6.28)
                cr.fill()


def main():
    os.environ.setdefault('XDG_RUNTIME_DIR', '/run/user/0')
    win = CountdownApp()
    win.show_all()
    Gtk.main()

if __name__ == '__main__':
    main()
