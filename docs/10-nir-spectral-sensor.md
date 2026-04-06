# AS7263 NIR Spectral Sensor — Bring-up & Cold Stimulus Test

## Overview

The AS7263 (ams-OSRAM) is a 6-channel near-infrared spectral sensor covering 610–860 nm. Each channel has a 20 nm FWHM narrowband filter, making it essentially a miniature spectrometer on a chip. It communicates via I2C at address **0x49** using a virtual register protocol.

This document covers sensor bring-up on the i.MX8MP EVK and an initial cold stimulus experiment for skin tissue monitoring.

## Hardware Setup

**Wiring on J21 (I2C3):**

| AS7263 Pin | J21 Pin | Signal |
|------------|---------|--------|
| 3.3V | Pin 1 | VEXT_3V3 |
| GND | Pin 9 | GND |
| SDA | Pin 3 | I2C3_SDA_3V3 |
| SCL | Pin 5 | I2C3_SCL_3V3 |

Pull-up resistors are built into the SparkFun Qwiic breakout board.

## Bring-up

### I2C Detection

Sensor detected immediately on first scan:

```
$ i2cdetect -y 2
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
40: -- -- -- -- -- -- -- -- -- 49 -- -- -- -- -- --
```

Chip identification via the virtual register protocol:

```
HW version: 0x40
FW version: 0x20
Sensor type: 0x3F (AS7263 NIR confirmed)
```

### Platform Adaptation

The Yocto image does not include `smbus2`, and the EVK has no internet access for pip. Rewrote the I2C interface using raw `/dev/i2c-2` with `fcntl.ioctl` — zero external dependencies:

```python
fd = os.open("/dev/i2c-2", os.O_RDWR)
fcntl.ioctl(fd, 0x0703, 0x49)   # I2C_SLAVE
os.write(fd, bytes([reg]))       # write register
data = os.read(fd, 1)[0]         # read byte
```

This also served as a good exercise in understanding how Linux exposes I2C hardware through character devices.

### Note on BME280

Before AS7263 testing, two GY-BME280 modules were debugged extensively on the same J21 pins — neither responded. The AS7263 working on the exact same wiring confirmed that the I2C bus, 3.3V power rail, and level shifters are all functional. The BME280 modules were defective (same batch, both dead).

Lesson learned: when an I2C device isn't detected, swap in a known-good device before diving into software debugging.

## Key Channels for Tissue Monitoring

| Channel | Wavelength | Role |
|---------|-----------|------|
| S | 680 nm | Deoxyhemoglobin (Hb) absorption peak — rises during ischemia |
| U | 760 nm | NIR reference, no special physiological significance |
| W | 860 nm | Oxyhemoglobin (HbO2) absorption peak — high when perfusion is good |

**Tissue Oxygenation Index:**

```
TOI = (W_860 - S_680) / (W_860 + S_680)
```

Cold exposure → vasoconstriction → less oxygenated blood → W drops, S rises → TOI decreases.

Raw TOI values are negative because the on-board LED has uneven spectral output (shorter wavelengths are brighter), so S is always larger than W in absolute terms. White-reference calibration would correct this. However, the **trend** (change over time) is still valid without calibration.

## Measurement Results

### Test Conditions

- **Gain:** 64x (maximum, needed for skin reflectance measurement)
- **Integration time:** 140 ms (INT_T = 50 × 2.8 ms)
- **LED:** 100 mA (required for skin — ambient light is blocked when sensor is pressed against skin)
- **Mode:** One-shot (mode 3), triggered every 2 seconds

### Finding: LED Must Be Enabled

With LED off, pressing the sensor against skin blocks all ambient light — the 860 nm channel drops to zero. Active illumination is mandatory for contact-mode skin measurements.

### Warm Skin Baseline (LED 100mA)

| Channel | Wavelength | Value (µW/cm²) |
|---------|-----------|-----------------|
| R | 610 nm | 9000 |
| S | 680 nm | 2780 |
| T | 730 nm | 582 |
| U | 760 nm | 374 |
| V | 810 nm | 490 |
| W | 860 nm | 405 |

Chip temperature: 38–39°C. TOI = −0.745. Signal stability: ±2% across 15 consecutive samples.

### Cold Stimulus — Short Exposure (2–3 min ice pack)

Applied ice pack to forearm, then immediately placed sensor on cooled skin. 15 samples collected.

| Metric | Warm | Cold | Change |
|--------|------|------|--------|
| Temperature | 38°C | 28→31°C | −10°C |
| S_680 | 2780 | 2500 | −10% |
| W_860 | 405 | 422 | +4% |
| TOI | −0.745 | −0.710 | +0.035 |

Short cold exposure reduced blood flow (S dropped 10%) but did not cause desaturation — consistent with mild, reversible vasoconstriction.

### Cold Stimulus — Extended Exposure (5 min ice pack)

Applied ice pack for 5 minutes, then monitored recovery for 1 minute (30 samples at 2s intervals).

| Time | Temp | S_680 | W_860 | V_810 | TOI |
|------|------|-------|-------|-------|-----|
| 0s | 28°C | 2941 | 518 | 644 | −0.700 |
| 15s | 29°C | 2900 | 500 | 617 | −0.706 |
| 30s | 30°C | 2889 | 476 | 578 | −0.718 |
| 45s | 31°C | 2882 | 460 | 556 | −0.725 |
| 60s | 33°C | 2811 | 432 | 514 | −0.734 |

![AS7263 Cold Stimulus Test](as7263_cold_test.png)

**Observations:**

1. Temperature recovered from 28°C to 33°C during sampling, confirming blood flow restoration
2. W_860 dropped 17% (518→432) during rewarming — counterintuitive at first glance
3. TOI shifted from −0.700 to −0.734 (more negative during recovery)
4. This pattern is consistent with **reactive hyperemia**: after cold stimulus is removed, blood vessels reopen and a surge of blood enters the tissue, temporarily increasing local oxygen consumption
5. 30 consecutive samples with zero communication errors — sensor is reliable

## Virtual Register Protocol

The AS7263 does not support direct I2C register access. All reads/writes go through three physical registers:

- `0x00` — Status register (TX_VALID / RX_VALID flags)
- `0x01` — Write register (send virtual address or data)
- `0x02` — Read register (retrieve response)

Each virtual register access requires polling the status register for readiness. If communication is interrupted mid-transaction (e.g., loose wire), the state machine desyncs and returns garbage data. The only recovery is a power cycle.

## Files

- `scripts/as7263_monitor.py` — Data acquisition script (raw I2C, no dependencies)
- `docs/as7263_cold_test.png` — Cold stimulus test charts

## White Reference Calibration

Before skin measurements, a white paper reference was taken to characterize the LED spectral profile. White paper has roughly uniform reflectance across 610–860 nm, so white-paper readings primarily reflect the LED's own spectral shape rather than sample properties. Dividing skin readings by this reference yields normalized tissue reflectance, removing the LED spectral bias.

Method: sensor face-down on standard A4 white paper, LED 100mA, 10 samples collected, last 6 averaged for stability.

| Channel | Wavelength | White Ref (µW/cm²) |
|---------|-----------|---------------------|
| R | 610 nm | 3449 |
| S | 680 nm | 938 |
| T | 730 nm | 231 |
| U | 760 nm | 165 |
| V | 810 nm | 249 |
| W | 860 nm | 193 |

The R:S:W ratio of 18:5:1 confirms severe LED spectral non-uniformity — this is why raw TOI is always negative.

**Calibrated TOI example** (warm skin baseline):

```
S_norm = 2780 / 938 = 2.96
W_norm = 405 / 193 = 2.10
TOI_cal = (2.10 - 2.96) / (2.10 + 2.96) = -0.170
```

After calibration, TOI shifts from −0.745 to −0.170, much closer to physiologically meaningful values.

## Known Issues

**Signal jitter in TOI curve:** The raw TOI plot shows noticeable sample-to-sample fluctuation (~±0.005). Two main causes:

1. **Contact pressure variation** — hand-held measurement means small movements change the optical path and reflection angle, causing readout fluctuation
2. **ADC quantization noise** — the AS7263 outputs calibrated IEEE754 floats, but the underlying ADC is 16-bit. On weaker channels like W_860, quantization steps become visible in the ratio calculation

Mitigation: apply a 3–5 point moving average to smooth the curve, or use a mechanical fixture to stabilize sensor-skin contact.

## Calibrated Skin Baseline

With the white reference established, skin readings can be normalized to remove LED spectral bias:

```
normalized_reflectance = skin_reading / white_reference
```

Forearm skin at room temperature, LED 100mA, 15 samples averaged:

| Metric | Raw | Calibrated | Note |
|--------|-----|------------|------|
| S_680 normalized | 2268 µW/cm² | 2.42 | skin / white_ref(938) |
| W_860 normalized | 302 µW/cm² | 1.56 | skin / white_ref(193) |
| TOI (raw) | −0.766 | — | dominated by LED spectral bias |
| TOI (calibrated) | — | **−0.215** | physiologically meaningful |
| Temperature | 31–32°C | | |

Observations:

1. Calibration shifted TOI by +0.55 (from −0.77 to −0.21), confirming that LED non-uniformity was the dominant factor in raw readings
2. TOI_cal stability across 15 samples: −0.19 to −0.22 (±0.015), good repeatability
3. Compared to the previous warm-hand session (38°C, TOI_cal = −0.17), today's baseline is slightly lower (32°C, TOI_cal = −0.21) — cooler skin means less blood flow, consistent with physiology
4. This establishes the room-temperature skin baseline at **TOI_cal ≈ −0.21** for future cold stimulus comparison

The calibration step is standard practice in diffuse reflectance spectroscopy — without it, the raw TOI is an artifact of the light source, not the tissue. The fact that calibrated values track skin temperature across sessions validates the measurement approach.

## Calibrated Cold Stimulus Test

Applied ice pack until skin was thoroughly cold (~5 min), then immediately placed sensor on cooled forearm. 30 samples with calibrated TOI:

| Time | Temp | TOI_raw | TOI_cal | vs baseline (−0.21) |
|------|------|---------|---------|---------------------|
| 0s | 25°C | −0.721 | −0.118 | +0.09 |
| 15s | 26°C | −0.726 | −0.128 | +0.08 |
| 30s | 27°C | −0.734 | −0.145 | +0.07 |
| 45s | 27°C | −0.744 | −0.167 | +0.04 |
| 60s | 29°C | −0.747 | −0.173 | +0.04 |

Observations:

1. **Cold skin TOI_cal (−0.12) is higher than warm baseline (−0.21)** — seemingly counterintuitive, but explained by physiology: vasoconstriction reduces total blood volume in the tissue. Both Hb and HbO2 decrease, but S_680 (Hb) drops proportionally more, shifting the normalized ratio upward
2. **TOI_cal drifts from −0.12 → −0.17 during rewarming** — reactive hyperemia again. Blood vessels reopen, oxygen-rich blood surges in but is consumed rapidly, temporarily lowering the oxygenation ratio
3. **Cross-session reproducibility confirmed**: warm baseline TOI_cal = −0.17 (previous session at 38°C) matches the rewarming endpoint here (−0.17 at 29°C), validating the calibration approach
4. Temperature rose from 25°C to 29°C during the 60s measurement window, consistent with active reperfusion

**Methodological note:** In this test, there was a delay between removing the ice pack and the start of data acquisition (sensor placement + script startup). The initial 25°C reading likely underestimates the peak cold because the skin had already begun rewarming. Future tests should use a countdown-triggered workflow to minimize this latency.

## Next Steps

- [x] White-paper calibration to normalize LED spectral profile
- [x] Establish room-temperature skin TOI baseline (TOI_cal ≈ −0.21)
- [x] Cold stimulus test with calibrated TOI — cold skin TOI_cal ≈ −0.12, reactive hyperemia confirmed
- [ ] Implement countdown-triggered measurement to capture true peak cold
- [ ] Determine frostbite warning threshold from experimental data
