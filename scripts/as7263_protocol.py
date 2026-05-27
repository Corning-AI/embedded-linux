#!/usr/bin/env python3
"""
AS7263 Cold Therapy Intensity Protocol — HDMI full-screen guide + capture.

Phases displayed on HDMI:
  1. PREP        (3s)              — get ready
  2. ICE ON      (ICE_SEC, default 12) — user applies ice, big countdown
  3. TRANSFER    (3s)              — remove ice + place sensor
  4. MEASURE     (N samples, ~2s each, default 30 = 60s) — live TOI/StO2
  5. DONE        — summary, ESC to close

CSV is printed to stdout (one row per sample) — redirect via SSH.

Usage:
    python3 as7263_protocol.py [ice_seconds] [num_samples] [run_label]
Defaults: 12s ice, 30 samples, label='12s'
"""

import os
import sys
import time
import math
import struct
import fcntl
import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

# Kill prior instances
for proc in ("as7263_countdown", "as7263_display", "as7263_protocol", "as7263_dashboard"):
    subprocess.run(["killall", "-9", proc], stderr=subprocess.DEVNULL)

ICE_SEC = int(sys.argv[1]) if len(sys.argv) > 1 else 12
NUM_SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 30
RUN_LABEL = sys.argv[3] if len(sys.argv) > 3 else f"{ICE_SEC}s"
PREP_SEC = 6
TRANSFER_SEC = 3

I2C_SLAVE = 0x0703
ADDR = 0x49
CALS = {'R': 0x14, 'S': 0x18, 'T': 0x1C, 'U': 0x20, 'V': 0x24, 'W': 0x28}
WREF = {'R': 3449, 'S': 938, 'T': 231, 'U': 165, 'V': 249, 'W': 193}
DPF_S = 3.0   # fingertip 680 nm
DPF_W = 2.5   # fingertip 860 nm
BASELINE_TOI_CAL = -0.21


class I2C:
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
            if (self.rb(0x00) & 0x02) == 0:
                break
            time.sleep(0.005)
        self.wb(0x01, r)
        for _ in range(100):
            if (self.rb(0x00) & 0x01) != 0:
                break
            time.sleep(0.005)
        return self.rb(0x02)

    def vw(self, r, v):
        for _ in range(100):
            if (self.rb(0x00) & 0x02) == 0:
                break
            time.sleep(0.005)
        self.wb(0x01, r | 0x80)
        for _ in range(100):
            if (self.rb(0x00) & 0x02) == 0:
                break
            time.sleep(0.005)
        self.wb(0x01, v)

    def rcal(self, a):
        b = [self.vr(a + i) for i in range(4)]
        raw = (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]
        return struct.unpack('!f', struct.pack('!I', raw))[0]

    def close(self):
        os.close(self.fd)


class App(Gtk.Window):
    def __init__(self):
        super().__init__(title="AS7263 Protocol")
        self.set_decorated(False)
        self.fullscreen()
        self.set_app_paintable(True)
        self.da = Gtk.DrawingArea()
        self.da.connect('draw', self.on_draw)
        self.add(self.da)
        self.connect('key-press-event', self.on_key)

        self.phase = 'prep'
        self.t_remain = PREP_SEC
        self.sample_n = 0
        self.last_toi_cal = 0.0
        self.last_sto2 = 0.0
        self.last_temp = 0
        self.samples = []  # (n, temp, toi_raw, toi_cal, sto2)
        self.lock = threading.Lock()
        self.running = True
        self.error_msg = ""

        GLib.timeout_add(100, self.refresh)
        GLib.timeout_add(1000, self.tick)
        self.connect('destroy', self.on_quit)

    def on_quit(self, *_a):
        self.running = False
        try:
            Gtk.main_quit()
        except Exception:
            pass

    def on_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.on_quit()

    def refresh(self):
        self.da.queue_draw()
        return self.running

    def tick(self):
        if self.phase == 'prep':
            self.t_remain -= 1
            if self.t_remain <= 0:
                self.phase = 'ice'
                self.t_remain = ICE_SEC
            return True
        elif self.phase == 'ice':
            self.t_remain -= 1
            if self.t_remain <= 0:
                self.phase = 'transfer'
                self.t_remain = TRANSFER_SEC
            return True
        elif self.phase == 'transfer':
            self.t_remain -= 1
            if self.t_remain <= 0:
                self.phase = 'measure'
                threading.Thread(target=self.measure_loop, daemon=True).start()
                return False
            return True
        return False

    def measure_loop(self):
        try:
            bus = I2C()
            bus.vw(0x07, 0x0B)  # LED 100mA
            bus.vw(0x04, (0x03 << 4) | (0x03 << 2))
            bus.vw(0x05, 50)
            print(f"# RUN={RUN_LABEL} ICE_SEC={ICE_SEC} N={NUM_SAMPLES} t_start={time.time():.3f}")
            print("# Note: chip_temp = AS7263 die temperature (LED+chip self-heating), NOT skin temperature")
            print("sample,R_610,S_680,T_730,U_760,V_810,W_860,chip_temp,toi_raw,toi_cal,sto2_dpf")
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
                    toi_raw = (w - s) / (w + s) if (w + s) > 0 else 0.0
                    sn = s / WREF['S']
                    wn = w / WREF['W']
                    toi_cal = (wn - sn) / (wn + sn) if (wn + sn) > 0 else 0.0
                    a_s = abs(math.log(WREF['S'] / max(s, 1.0))) / DPF_S
                    a_w = abs(math.log(WREF['W'] / max(w, 1.0))) / DPF_W
                    sto2 = a_w / (a_w + a_s) if (a_w + a_s) > 0 else 0.0
                    with self.lock:
                        self.sample_n = n
                        self.last_toi_cal = toi_cal
                        self.last_sto2 = sto2
                        self.last_temp = temp
                        self.samples.append((n, temp, toi_raw, toi_cal, sto2))
                    print(f"{n},{ch['R']:.0f},{ch['S']:.0f},{ch['T']:.0f},"
                          f"{ch['U']:.0f},{ch['V']:.0f},{ch['W']:.0f},"
                          f"{temp},{toi_raw:.4f},{toi_cal:.4f},{sto2:.4f}",
                          flush=True)
                except OSError as e:
                    with self.lock:
                        self.error_msg = str(e)
                time.sleep(1.65)
            bus.vw(0x07, 0x00)
            bus.close()
        except Exception as e:
            with self.lock:
                self.error_msg = str(e)
            print(f"# ERR: {e}", flush=True)
        with self.lock:
            self.phase = 'done'

    def on_draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        # bg
        cr.set_source_rgb(0.05, 0.05, 0.08)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        with self.lock:
            phase = self.phase
            t_remain = self.t_remain
            sample_n = self.sample_n
            toi_cal = self.last_toi_cal
            sto2 = self.last_sto2
            temp = self.last_temp
            samples = list(self.samples)
            err = self.error_msg

        cr.select_font_face("Sans")

        def center_text(text, y_frac, size_frac, rgb):
            cr.set_source_rgb(*rgb)
            cr.set_font_size(int(h * size_frac))
            ext = cr.text_extents(text)
            cr.move_to((w - ext.width) / 2, h * y_frac)
            cr.show_text(text)

        if phase == 'prep':
            center_text("GET READY", 0.30, 0.10, (0.7, 0.7, 0.9))
            center_text(f"{t_remain}", 0.70, 0.30, (1, 1, 1))
            center_text(f"Run {RUN_LABEL} · {ICE_SEC}s ice ahead", 0.92, 0.04, (0.5, 0.5, 0.6))

        elif phase == 'ice':
            center_text("APPLY ICE TO FINGERTIP", 0.25, 0.08, (0.3, 0.7, 1.0))
            center_text(f"{t_remain}", 0.65, 0.40, (1, 1, 1))
            center_text("seconds remaining", 0.85, 0.04, (0.6, 0.6, 0.7))
            center_text(f"Phase 1/3 · Run {RUN_LABEL}", 0.95, 0.03, (0.4, 0.4, 0.5))

        elif phase == 'transfer':
            center_text("REMOVE ICE → PLACE SENSOR", 0.30, 0.07, (1.0, 0.7, 0.2))
            center_text(f"{t_remain}", 0.70, 0.30, (1, 1, 1))
            center_text("Phase 2/3 · sensor will start at 0", 0.92, 0.03, (0.5, 0.5, 0.5))

        elif phase == 'measure':
            center_text(f"MEASURING — {sample_n}/{NUM_SAMPLES}", 0.10, 0.06, (0.2, 0.9, 0.5))
            cr.set_source_rgb(1, 1, 1)
            cr.set_font_size(int(h * 0.11))
            cr.move_to(w * 0.05, h * 0.30)
            cr.show_text(f"TOI_cal:  {toi_cal:+.4f}")
            cr.move_to(w * 0.05, h * 0.45)
            color_sto2 = (0.3, 0.8, 0.3) if sto2 < 0.40 else (1.0, 0.8, 0.3) if sto2 < 0.43 else (1.0, 0.3, 0.3)
            cr.set_source_rgb(*color_sto2)
            cr.show_text(f"StO2:     {sto2:.3f}")
            cr.set_source_rgb(0.7, 0.7, 0.7)
            cr.set_font_size(int(h * 0.06))
            cr.move_to(w * 0.05, h * 0.60)
            cr.show_text(f"(historical baseline TOI_cal ≈ {BASELINE_TOI_CAL:+.2f})")
            # mini-curve
            if len(samples) > 1:
                xs = [s[0] for s in samples]
                ys = [s[3] for s in samples]
                xmin = 1
                xmax = max(NUM_SAMPLES, 5)
                ymin = min(min(ys), -0.25)
                ymax = max(max(ys), 0.0)
                yrange = max(ymax - ymin, 0.05)
                gx0 = w * 0.05
                gy0 = h * 0.70
                gw = w * 0.90
                gh = h * 0.22
                # axes
                cr.set_source_rgb(0.3, 0.3, 0.4)
                cr.set_line_width(1)
                cr.rectangle(gx0, gy0, gw, gh)
                cr.stroke()
                # baseline line
                if ymin < BASELINE_TOI_CAL < ymax:
                    yb = gy0 + (ymax - BASELINE_TOI_CAL) / yrange * gh
                    cr.set_source_rgb(0.5, 0.5, 0.5)
                    cr.set_dash([4, 4])
                    cr.move_to(gx0, yb)
                    cr.line_to(gx0 + gw, yb)
                    cr.stroke()
                    cr.set_dash([])
                # data
                cr.set_source_rgb(0.3, 0.7, 1.0)
                cr.set_line_width(2)
                px0 = gx0 + (xs[0] - xmin) / (xmax - xmin) * gw
                py0 = gy0 + (ymax - ys[0]) / yrange * gh
                cr.move_to(px0, py0)
                for i in range(1, len(xs)):
                    px = gx0 + (xs[i] - xmin) / (xmax - xmin) * gw
                    py = gy0 + (ymax - ys[i]) / yrange * gh
                    cr.line_to(px, py)
                cr.stroke()

            if err:
                center_text(f"ERR: {err[:60]}", 0.97, 0.025, (1, 0.3, 0.3))

        elif phase == 'done':
            center_text("✓ DONE", 0.20, 0.10, (0.2, 0.9, 0.5))
            cr.set_source_rgb(1, 1, 1)
            cr.set_font_size(int(h * 0.06))
            cr.move_to(w * 0.10, h * 0.40)
            cr.show_text(f"Run:           {RUN_LABEL}")
            cr.move_to(w * 0.10, h * 0.50)
            cr.show_text(f"Final TOI_cal: {toi_cal:+.4f}")
            cr.move_to(w * 0.10, h * 0.60)
            cr.show_text(f"Final StO2:    {sto2:.3f}")
            # endpoint vs baseline
            delta = toi_cal - BASELINE_TOI_CAL
            cr.move_to(w * 0.10, h * 0.70)
            cr.set_source_rgb(0.7, 0.9, 0.7)
            cr.show_text(f"Δ vs baseline: {delta:+.3f}")
            center_text("Press ESC to close", 0.92, 0.035, (0.5, 0.5, 0.5))


def main():
    os.environ.setdefault('XDG_RUNTIME_DIR', '/run/user/0')
    win = App()
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
