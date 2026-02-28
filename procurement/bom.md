# Hardware BOM

Bill of materials for the i.MX 8M Plus sensor platform.

## Core Board

| # | Item | Part Number | Qty | Notes |
|---|------|-------------|-----|-------|
| 1 | NXP i.MX 8M Plus EVK | 8MPLUSLPD4-EVK | 1 | Main dev board. LPDDR4 6 GB + eMMC. Includes 12 V PSU and USB-C cable. |
| 2 | OV5640 MIPI CSI camera + adapter | MINISASTOCSI | 1 | NXP official camera module. 5MP, 1080p@30fps. Connects to J801 via mini-SAS cable. |

## Sensors

| # | Item | Part Number | Qty | Notes |
|---|------|-------------|-----|-------|
| 3 | BME280 breakout (I2C, 3.3 V) | GY-BME280-3.3 | 2 | Temp/humidity/pressure. Goes on I2C3 (A53 Linux side). |
| 4 | MPU6050 6-axis IMU breakout | GY-521 | 2 | Accel + gyro. Goes on I2C2 (M7 FreeRTOS side). |
| 5 | SSD1306 0.96" OLED (I2C, white) | — | 2 | 128x64 white OLED. Shares I2C2 bus with MPU6050. |
| 6 | ADXL345 3-axis accelerometer | GY-291 | 2 | For SPI kernel driver development on A53 Linux side. |

## Tools and Cables

| # | Item | Part Number | Qty | Notes |
|---|------|-------------|-----|-------|
| 7 | FTDI 3.3 V USB-UART cable (6-pin) | TTL-232R-3V3 | 1 | Backup debug serial. **Must be 3.3 V — 5 V will fry the SoC GPIOs.** |
| 8 | USB logic analyzer (4-in-1) | SLOGIC4IN1 | 1 | Logic analyzer + DAPLink + UART module. For I2C/SPI signal debugging. |
| 9 | Micro USB data cable | — | 1 | For EVK J23 debug serial console (board has built-in FTDI chip). |
| 10 | USB-C SD/TF card reader | — | 1 | For flashing Yocto images from PC to SD card. |

## Storage

| # | Item | Part Number | Qty | Notes |
|---|------|-------------|-----|-------|
| 11 | SanDisk High Endurance microSD 64 GB | SDSQQNR-064G | 1 | For Yocto image boot. High endurance for repeated flashing. |

## From Lab

- Dupont jumper wires (male-male, male-female, female-female)
- Ethernet cable
- Multimeter

## Notes

- All sensor breakouts run at 3.3 V logic — do **not** connect 5 V modules to the EVK GPIO header.
- The EVK box includes a 12 V / 5 A power adapter and a USB-C cable (for J6 OTG flashing).
- J23 (Micro USB) is the primary debug port — the built-in FTDI chip provides 4 serial ports over a single USB connection.
- Extra sensor quantities serve as spares in case of wiring mistakes.
