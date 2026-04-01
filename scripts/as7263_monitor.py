#!/usr/bin/env python3
"""
AS7263 冷敷皮肤监测

目的：通过NIR光谱监测冷敷过程中皮肤组织灌注变化，预警冻伤风险
原理：Hb(脱氧)在680nm吸收强, HbO2(含氧)在860nm吸收强
      冷敷 → 血管收缩 → 灌注下降 → TOI下降

参考：SparkFun AS726X Arduino Library - Example1_BasicReadings
      AS726X.h 寄存器定义 (virtual register protocol)
      AS7263 Datasheet (ams-OSRAM)

平台：i.MX8MP EVK, Python 3, I2C3 (J21)
接线：AS7263 SDA -> J21 Pin3, SCL -> J21 Pin5, 3.3V -> Pin1, GND -> Pin9

Ning Kang, 2026-03-10
"""

import os
import time
import struct
import fcntl

# === I2C raw interface (no smbus2 needed) ===
I2C_SLAVE = 0x0703  # ioctl to set slave address


class RawI2C:
    """Raw I2C via /dev/i2c-N using ioctl + file I/O.
    No external Python packages required — only needs fcntl (built-in)."""

    def __init__(self, bus_num, addr):
        self.fd = os.open(f"/dev/i2c-{bus_num}", os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, addr)

    def close(self):
        os.close(self.fd)

    def read_byte_data(self, reg):
        """SMBus read_byte_data: write register addr, read 1 byte back."""
        os.write(self.fd, bytes([reg]))
        return os.read(self.fd, 1)[0]

    def write_byte_data(self, reg, value):
        """SMBus write_byte_data: write register addr + value."""
        os.write(self.fd, bytes([reg, value]))


# === AS7263 寄存器定义 (来自SparkFun AS726X.h) ===
AS726X_ADDR = 0x49
SLAVE_STATUS_REG = 0x00
SLAVE_WRITE_REG  = 0x01
SLAVE_READ_REG   = 0x02
TX_VALID = 0x02
RX_VALID = 0x01

CONTROL_SETUP = 0x04
INT_T = 0x05
DEVICE_TEMP = 0x06

# AS7263校准值寄存器 (4字节IEEE754 float)
CAL_REGS = {
    'R': 0x14,  # 610nm
    'S': 0x18,  # 680nm - Hb脱氧血红蛋白吸收峰
    'T': 0x1C,  # 730nm
    'U': 0x20,  # 760nm
    'V': 0x24,  # 810nm - 近等吸收点
    'W': 0x28,  # 860nm - HbO2含氧血红蛋白吸收峰
}

SENSORTYPE_AS7263 = 0x3F
TOI_WARNING = 0.3


def virtual_read(bus, reg):
    """读取虚拟寄存器 - 翻译自SparkFun AS726X.cpp
    AS7263不是普通I2C直接读写，所有访问经过0x00/0x01/0x02三个寄存器中转"""
    for _ in range(100):
        status = bus.read_byte_data(SLAVE_STATUS_REG)
        if (status & TX_VALID) == 0:
            break
        time.sleep(0.005)
    bus.write_byte_data(SLAVE_WRITE_REG, reg)
    for _ in range(100):
        status = bus.read_byte_data(SLAVE_STATUS_REG)
        if (status & RX_VALID) != 0:
            break
        time.sleep(0.005)
    return bus.read_byte_data(SLAVE_READ_REG)


def virtual_write(bus, reg, value):
    """写入虚拟寄存器"""
    for _ in range(100):
        status = bus.read_byte_data(SLAVE_STATUS_REG)
        if (status & TX_VALID) == 0:
            break
        time.sleep(0.005)
    bus.write_byte_data(SLAVE_WRITE_REG, reg | 0x80)
    for _ in range(100):
        status = bus.read_byte_data(SLAVE_STATUS_REG)
        if (status & TX_VALID) == 0:
            break
        time.sleep(0.005)
    bus.write_byte_data(SLAVE_WRITE_REG, value)


def read_calibrated(bus, cal_addr):
    """读取4字节校准值，返回float (uW/cm2)"""
    b = [virtual_read(bus, cal_addr + i) for i in range(4)]
    raw = (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]
    return struct.unpack('!f', struct.pack('!I', raw))[0]


def main():
    I2C_BUS = 2  # i2c-2 = I2C3 = J21 on i.MX8MP EVK

    bus = RawI2C(I2C_BUS, AS726X_ADDR)
    try:
        # 检查传感器型号
        hw_ver = virtual_read(bus, 0x00)
        fw_ver = virtual_read(bus, 0x02)
        print(f"[INFO] HW version: 0x{hw_ver:02X}, FW version: 0x{fw_ver:02X}")

        sensor_type = virtual_read(bus, 0x01)
        if sensor_type != SENSORTYPE_AS7263:
            print(f"[WARN] sensor type=0x{sensor_type:02X}, expected 0x3F (AS7263)")
        else:
            print("[OK] AS7263 (NIR) connected")

        # 配置：增益=64x, 测量模式=单次(mode 3)
        ctrl = (0x03 << 4) | (0x03 << 2)  # gain=64x, mode=one-shot
        virtual_write(bus, CONTROL_SETUP, ctrl)
        virtual_write(bus, INT_T, 50)  # 积分时间 = 2.8ms x 50 = 140ms
        print("[CONFIG] gain=64x, integration=140ms, one-shot mode")

        print("\nSample,R_610,S_680,T_730,U_760,V_810,W_860,Temp,TOI,Warning")

        n = 0
        while True:
            # 触发单次测量
            ctrl_val = virtual_read(bus, CONTROL_SETUP)
            virtual_write(bus, CONTROL_SETUP, (ctrl_val & 0xF3) | 0x0C)
            time.sleep(0.3)

            # 读6通道校准值
            ch = {k: read_calibrated(bus, v) for k, v in CAL_REGS.items()}
            temp = virtual_read(bus, DEVICE_TEMP)

            # TOI = (W_860 - S_680) / (W_860 + S_680)
            s, w = ch['S'], ch['W']
            toi = (w - s) / (w + s) if (w + s) > 0 else 0
            warning = "LOW!" if toi < TOI_WARNING else "OK"

            n += 1
            print(f"{n},{ch['R']:.2f},{ch['S']:.2f},{ch['T']:.2f},"
                  f"{ch['U']:.2f},{ch['V']:.2f},{ch['W']:.2f},"
                  f"{temp},{toi:.4f},{warning}")

            time.sleep(2)
    except KeyboardInterrupt:
        print(f"\n[DONE] {n} samples collected")
    finally:
        bus.close()


if __name__ == '__main__':
    main()
