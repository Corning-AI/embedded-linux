# 04 — FreeRTOS on the Cortex-M7

## What's going on here

The i.MX 8M Plus is a heterogeneous multi-core SoC:

- **Cortex-A53 x4** — runs Linux, handles application-level work
- **Cortex-M7 x1** — runs FreeRTOS or bare-metal code, handles real-time control

The M7 core executes out of its own TCM (Tightly Coupled Memory), completely independent of Linux. It isn't affected by Linux scheduling, page faults, or any other OS jitter — so you can hit microsecond-level real-time response without breaking a sweat.

## Getting the MCUXpresso SDK

### Option 1: west (recommended)

```bash
mkdir -p ~/mcuxsdk && cd ~/mcuxsdk
west init -m https://github.com/nxp-mcuxpresso/mcux-sdk-examples --mr main
west update
cd mcux-sdk-examples
```

### Option 2: NXP website download

1. Go to <https://mcuxpresso.nxp.com/>
2. Select Board: **EVK-MIMX8MP**
3. Check FreeRTOS and the driver components you need
4. Download the SDK package

## SDK directory layout

```
mcux-sdk-examples/
├── boards/
│   └── evkmimx8mp/
│       ├── demo_apps/
│       │   ├── hello_world/
│       │   └── sai_low_power_audio/
│       ├── driver_examples/
│       │   ├── i2c/
│       │   ├── spi/
│       │   └── uart/
│       ├── multicore_examples/
│       │   └── rpmsg_lite_str_echo_rtos/
│       └── freertos_examples/
│           ├── freertos_hello/
│           └── freertos_generic/
├── CMSIS/
├── devices/
│   └── MIMX8ML8/
└── middleware/
    └── multicore/
        └── rpmsg_lite/
```

## Building the hello_world example

```bash
cd boards/evkmimx8mp/demo_apps/hello_world/armgcc
export ARMGCC_DIR=/opt/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi
./build_release.sh
ls release/hello_world.bin
ls release/hello_world.elf
```

### Build targets

| Target | Memory | Notes |
|--------|--------|-------|
| `debug` | TCM | Debug build, no optimization |
| `release` | TCM | Optimized |
| `ddr_debug` | DDR | Debug build, runs from DDR |
| `ddr_release` | DDR | Optimized, runs from DDR |

TCM starts at `0x7E0000` — it's fast but small (~256 KB). DDR gives you much more space but higher latency. For real-time tasks, I stick with TCM unless the firmware simply won't fit.

## Loading M7 firmware

### Option 1: U-Boot

This one's straightforward — you load the `.bin` before Linux boots:

```
fatload mmc 1:1 0x7e0000 hello_world.bin
bootaux 0x7e0000
```

### Option 2: Linux remoteproc

Load (and reload) the firmware at runtime from Linux:

```bash
cp hello_world.elf /lib/firmware/
echo hello_world.elf > /sys/class/remoteproc/remoteproc0/firmware
echo start > /sys/class/remoteproc/remoteproc0/state
cat /sys/class/remoteproc/remoteproc0/state
echo stop > /sys/class/remoteproc/remoteproc0/state
```

### Comparison

| | U-Boot | remoteproc |
|---|---|---|
| When it loads | Before Linux boots | While Linux is running |
| File format | `.bin` | `.elf` |
| Good for | Early development, quick tests | Production deployment |
| Reload without reboot? | No | Yes — start/stop dynamically |

For day-to-day development I've been using remoteproc because I can iterate on the M7 firmware without rebooting the whole board.

## RPMsg: talking between cores

### How it works

```
A53 (Linux)                    M7 (FreeRTOS)
    |                              |
    |  <-- shared memory (DDR) --> |
    |                              |
  /dev/ttyRPMSG0  <-- RPMsg -->  rpmsg_lite
```

Under the hood it's shared memory plus inter-core interrupts. The Linux side exposes it as a TTY device; the M7 side uses the `rpmsg_lite` library from NXP's multicore middleware.

### Building the RPMsg echo example

```bash
cd boards/evkmimx8mp/multicore_examples/rpmsg_lite_str_echo_rtos/armgcc
./build_release.sh
```

### Running RPMsg communication

1. Load the firmware via remoteproc:

```bash
cp rpmsg_lite_str_echo_rtos.elf /lib/firmware/
echo rpmsg_lite_str_echo_rtos.elf > /sys/class/remoteproc/remoteproc0/firmware
echo start > /sys/class/remoteproc/remoteproc0/state
```

2. Send and receive from the Linux side:

```bash
ls /dev/ttyRPMSG*
echo "Hello from Linux" > /dev/ttyRPMSG0
cat /dev/ttyRPMSG0
```

If everything's working, the M7 echoes back whatever you send.

### Device Tree configuration

The device tree needs reserved memory regions for the vring buffers and resource table. Here's what mine looks like:

```dts
&rpmsg {
    status = "okay";
};

reserved-memory {
    m7_reserved: m7@0x80000000 {
        no-map;
        reg = <0 0x80000000 0 0x1000000>;
    };
    vdev0vring0: vdev0vring0@55000000 {
        reg = <0 0x55000000 0 0x8000>;
        no-map;
    };
    vdev0vring1: vdev0vring1@55008000 {
        reg = <0 0x55008000 0 0x8000>;
        no-map;
    };
    rsc_table: rsc-table@550ff000 {
        reg = <0 0x550ff000 0 0x1000>;
        no-map;
    };
};
```

The `no-map` property keeps Linux from touching these memory ranges — they belong to the M7 and the RPMsg transport.

## Project idea: MPU6050 real-time sampling

### Goal

Run FreeRTOS on the M7 core. Read an MPU6050 IMU over I2C (or SPI) at 1 kHz with hard real-time guarantees. Forward the data to the A53 via RPMsg.

### Task architecture

```
FreeRTOS Tasks:
┌─────────────────────────┐
│ Task 1: Sensor Read     │  <-- highest priority, 1 ms period
│  - I2C/SPI read MPU6050 │
│  - store in ring buffer │
├─────────────────────────┤
│ Task 2: Data Pack       │  <-- medium priority
│  - read from buffer     │
│  - pack into struct     │
├─────────────────────────┤
│ Task 3: RPMsg Send      │  <-- low priority
│  - send to A53 via RPMsg│
├─────────────────────────┤
│ Task 4: OLED Display    │  <-- lowest priority
│  - display on SSD1306   │
└─────────────────────────┘
```

The priority ordering matters: sensor acquisition must never be starved by display updates or RPMsg transfers. I chose a ring buffer between Task 1 and Task 2 so the sensor read task can finish as fast as possible and never block.

### Packet format

```c
typedef struct {
    uint32_t timestamp_us;
    int16_t  accel_x;
    int16_t  accel_y;
    int16_t  accel_z;
    int16_t  gyro_x;
    int16_t  gyro_y;
    int16_t  gyro_z;
    uint16_t checksum;
} __attribute__((packed)) mpu6050_packet_t;
```

At 1 kHz, each packet is 20 bytes — that's 20 KB/s, well within what RPMsg can handle.

## Debugging tips

The M7's `PRINTF` output goes to **J23 / ttyUSB3** by default. On my setup:

```bash
picocom -b 115200 /dev/ttyUSB3
```

### Common issues

1. **M7 starts but no output** — Double-check the `.bin` load address. For TCM it must be `0x7E0000`. Loading to the wrong address is a silent failure; the core just runs garbage.

2. **RPMsg device doesn't appear (`/dev/ttyRPMSG*` missing)** — Check your device tree: make sure the `rpmsg` node has `status = "okay"` and the reserved memory regions are correct.

3. **I2C bus not responding** — The A53 and M7 can't share the same I2C bus simultaneously. If Linux has a driver bound to that bus, the M7 won't be able to use it. Either disable the bus in the Linux device tree or assign separate buses to each core.
