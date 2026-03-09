# 08 — Device Tree 通俗解读

## 什么是 Device Tree？

Device tree 不是程序，不会被"执行"。它是一张**硬件说明书**，告诉 Linux 内核："这块板子上有哪些东西、接在哪里、怎么配置"。

你可以把它类比为**原理图的文字版** — 原理图给人看，device tree 给内核看。

## 源文件位置

- **板级文件**: [`imx8mp-evk.dts`](https://github.com/nxp-imx/linux-imx/blob/lf-6.6.y/arch/arm64/boot/dts/freescale/imx8mp-evk.dts) — EVK 板上有什么
- **芯片级文件**: [`imx8mp.dtsi`](https://github.com/nxp-imx/linux-imx/blob/lf-6.6.y/arch/arm64/boot/dts/freescale/imx8mp.dtsi) — i.MX8MP SoC 里有什么

关系：`.dts` include `.dtsi`，板级文件**覆盖**芯片级定义。

## 文件整体结构（1476 行，5 大块）

```
imx8mp-evk.dts
│
├── 第 1 块：板子自身的东西        (行 1~290)
│   └── 内存、电源开关、LED、音频、USB Type-C
│
├── 第 2 块：覆盖 SoC 外设配置     (行 291~700)
│   └── 网口、CAN、I2C、SPI、UART、SD卡、USB
│
├── 第 3 块：显示 + 摄像头          (行 700~1000)
│   └── HDMI、MIPI DSI、LVDS、CSI 摄像头
│
├── 第 4 块：GPU / VPU / NPU       (行 1000~1050)
│   └── 全部 status = "okay" 启用
│
└── 第 5 块：引脚复用 (pinctrl)     (行 1050~1476)
    └── 每个引脚被分配成什么功能
```

---

## 第 1 块：板子自身的东西（"我是谁"）

```dts
/ {
    model = "NXP i.MX8MPlus EVK board";               // 板子名字
    compatible = "fsl,imx8mp-evk", "fsl,imx8mp";      // 身份标识

    #include "imx8mp.dtsi"    // 引入芯片级定义（SoC 里有什么）
```

这就像原理图封面页 — "这是 NXP 的 i.MX8MP 评估板"。

然后定义板上特有的东西（不是芯片自带的）：

| 节点 | 是什么 | 通俗解释 |
|------|--------|---------|
| `memory@40000000` | 内存 | "板子上焊了 6GB LPDDR4，从地址 0x40000000 开始" |
| `gpio-leds` | LED 灯 | "板上有颗黄色状态灯，接在 GPIO3_16" |
| `reg_usdhc2_vmmc` | 电源开关 | "SD 卡槽的 3.3V 供电由 GPIO2_19 控制" |
| `reg_can1_stby` | 电源开关 | "CAN 总线收发器的待机脚" |
| `reg_usb_vbus` | 电源开关 | "USB VBUS 5V 由 GPIO1_14 控制" |
| `sound-wm8960` | 音频系统 | "板子上有 WM8960 音频编解码器，接耳机和喇叭" |
| `sound-hdmi` | HDMI 音频 | "HDMI 也能出声音" |

> **关于 `regulator-fixed`**: 它们全是用 GPIO 控制的电源开关。和 STM32 项目里用 GPIO 使能 LDO 完全一样的概念。区别是在 Linux 里，这些被抽象成了 `regulator` 子系统，驱动通过 `regulator_enable()` 调用而不是直接操作 GPIO。

---

## 第 2 块：覆盖 SoC 外设配置（"芯片里的东西，在这块板上怎么接"）

这部分全是 `&xxx` 开头的节点 — 意思是**修改**芯片级 `.dtsi` 里已经定义的外设。

### I2C 部分（重点）

#### I2C1 (i2c-0) — 系统电源管理

```dts
&i2c1 {
    clock-frequency = <400000>;        // 400 kHz Fast Mode
    pinctrl-0 = <&pinctrl_i2c1>;       // 用哪组引脚
    status = "okay";                   // 启用

    pmic@25 {                          // I2C 地址 0x25 上挂了一颗 PMIC
        compatible = "nxp,pca9450c";   // 内核靠这个字符串找驱动
        reg = <0x25>;                  // I2C 从机地址
        regulators { ... };            // PMIC 能输出哪些电压（6 路 buck/LDO）
    };
};
```

#### I2C2 (i2c-1) — 显示 + 摄像头

```dts
&i2c2 {
    clock-frequency = <400000>;
    status = "okay";

    adv7535@3d {                        // HDMI 桥接芯片
        compatible = "adi,adv7535";
        reg = <0x3d>;
    };

    ov5640_mipi@3c {                    // ← OV5640 摄像头
        compatible = "ovti,ov5640";     // 内核匹配 drivers/media/i2c/ov5640.c
        reg = <0x3c>;                   // I2C 地址（i2cdetect 能看到）
        powerdown-gpios = <&gpio2 11 GPIO_ACTIVE_HIGH>;
        reset-gpios = <&gpio1 6 GPIO_ACTIVE_LOW>;
        status = "okay";               // "okay" = 启用
    };
};
```

#### I2C3 (i2c-2) — 音频 + GPIO 扩展器（也是我们的传感器总线）

```dts
&i2c3 {
    clock-frequency = <400000>;
    status = "okay";

    gpio@20 {                           // GPIO 扩展器（i2cdetect 显示 0x20 UU）
        compatible = "ti,tca6416";
        reg = <0x20>;
    };

    wm8960@1a {                         // 音频编解码器（i2cdetect 显示 0x1a UU）
        compatible = "wlf,wm8960";
        reg = <0x1a>;
    };

    // 注意：这里还没有 BME280 节点！
    // Phase 2 的目标就是在这里添加一个：
    //
    //   bme280@76 {
    //       compatible = "bosch,bme280";
    //       reg = <0x76>;
    //       status = "okay";
    //   };
};
```

#### 每个 I2C 设备节点的统一模式

```
设备名@地址 {
    compatible = "厂商,型号";    ← 内核靠这个找驱动（字符串匹配）
    reg = <地址>;                ← I2C 从机地址
    status = "okay";             ← 启用（"disabled" = 禁用）
    // ... 其他配置（GPIO、时钟等）
};
```

> **`UU` vs 普通地址**: `i2cdetect` 显示 `UU` 表示该地址的设备已被内核驱动绑定（设备树里有节点 + 内核有匹配的驱动）。普通数字（如 `50`）表示设备存在但没有驱动绑定（设备树里没有声明或没有匹配的驱动）。

### 网口部分

```dts
&eqos {                              // 千兆以太网 1（J11A，带 TSN）
    phy-mode = "rgmii-id";           // RGMII 接口，内部延迟
    phy-handle = <&ethphy0>;         // 指向下面的 PHY 芯片
    status = "okay";

    mdio {
        ethphy0: ethernet-phy@1 {
            reset-gpios = <&gpio4 22 GPIO_ACTIVE_LOW>;
        };
    };
};

&fec {                               // 千兆以太网 2（J10）
    phy-mode = "rgmii-id";
    status = "okay";
};
```

### 其他外设一览

| 节点 | 是什么 | EVK 上的接口 | 状态 |
|------|--------|-------------|------|
| `&ecspi2` | SPI 接口 | 板上 SPI 设备 | okay |
| `&flexcan1` | CAN 总线 1 | CAN 收发器 | okay |
| `&flexcan2` | CAN 总线 2 | — | **disabled**（和 PDM 麦克风引脚冲突） |
| `&uart1` | 串口 1 | 蓝牙（88W8997-bt） | okay |
| `&uart2` | 串口 2 | **串口终端**（COM5） | okay |
| `&usdhc2` | SD 卡控制器 | SD 卡槽 (J3) | okay |
| `&usdhc3` | eMMC 控制器 | 板载 32GB eMMC | okay |
| `&usb_dwc3_0` | USB3 端口 0 | J5 (Type-C), OTG 模式 | okay |
| `&usb_dwc3_1` | USB3 端口 1 | J6 (Type-C), Host 模式 | okay |
| `&i2c5` | I2C 扩展 | J22 | **disabled**（和 CAN1 引脚冲突） |

---

## 第 3 块：显示 + 摄像头（"看得见的东西"）

```dts
&hdmi { status = "okay"; };          // HDMI 输出 (J17)
&hdmiphy { status = "okay"; };       // HDMI 物理层
&lcdif3 { status = "okay"; };        // LCD 控制器（驱动 HDMI）

&mipi_csi_0 {                        // MIPI 摄像头接口 1 (J12)
    status = "okay";
    port {
        mipi_csi0_ep: endpoint {
            remote-endpoint = <&ov5640_mipi_0_ep>;  // 指向 OV5640
            data-lanes = <2>;                        // 2 条数据 lane
        };
    };
};

&mipi_csi_1 { status = "disabled"; }; // 摄像头接口 2 (J13) — 默认关闭
```

> **`remote-endpoint` 双向引用**: OV5640 节点里有 `remote-endpoint = <&mipi_csi0_ep>`，CSI 节点里有 `remote-endpoint = <&ov5640_mipi_0_ep>`。就像原理图上两个接插件之间的连线。内核通过这个双向引用知道"摄像头数据从哪里流到哪里"。

---

## 第 4 块：GPU / VPU / NPU（"加速器全开"）

```dts
&gpu_3d { status = "okay"; };        // 3D GPU (Vivante GC7000UL)
&gpu_2d { status = "okay"; };        // 2D GPU
&vpu_g1 { status = "okay"; };        // 视频解码器
&vpu_g2 { status = "okay"; };        // 视频解码器
&vpu_vc8000e { status = "okay"; };   // 视频编码器
&ml_vipsi { status = "okay"; };      // NPU (2.3 TOPS)
```

---

## 第 5 块：引脚复用 pinctrl（"哪根线干什么活"）

占了文件将近 1/3（约 400 行），全是这种格式：

```dts
pinctrl_i2c3: i2c3grp {
    fsl,pins = <
        MX8MP_IOMUXC_I2C3_SCL__I2C3_SCL    0x400001c2
        MX8MP_IOMUXC_I2C3_SDA__I2C3_SDA    0x400001c2
    >;
};
```

含义：

- `MX8MP_IOMUXC_I2C3_SCL__I2C3_SCL` = "把 I2C3_SCL 这根引脚配置成 I2C3 的 SCL 功能"
- `0x400001c2` = pad 配置寄存器值（上拉、驱动强度、开漏等）

这就像 STM32CubeMX 里的引脚配置界面 — 每根引脚可以有多种功能（GPIO、I2C、UART...），这里确定它具体干什么。在 STM32 里写 `GPIO_InitStruct.Alternate = GPIO_AF4_I2C1`，在 device tree 里就是这种写法。

---

## 一张图总结

```
imx8mp-evk.dts 在说什么？

"我是 NXP i.MX8MP EVK"             → compatible
"内存 6GB，从这个地址开始"           → memory
"板上有这些额外的电源开关和 LED"     → regulator-fixed, gpio-leds
"芯片里的 I2C1 启用，上面挂了 PMIC"  → &i2c1 { pmic@25 }
"芯片里的 I2C2 启用，挂了摄像头"     → &i2c2 { ov5640@3c }
"芯片里的 I2C3 启用，挂了音频和GPIO" → &i2c3 { wm8960@1a, gpio@20 }
"网口、SD卡、USB、HDMI 全部启用"     → &eqos, &usdhc2, &usb, &hdmi
"摄像头 1 启用，摄像头 2 关闭"       → &mipi_csi_0 okay, _1 disabled
"GPU、VPU、NPU 全开"               → status = "okay"
"最后，每根引脚的功能分配表"         → &iomuxc { pinctrl_xxx }
```

## 与 i2cdetect 的对应关系

在 EVK 上运行 `i2cdetect -y 2`（扫描 I2C3）：

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- UU -- -- -- -- --
20: UU -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
50: 50 -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
```

| 地址 | i2cdetect | 设备树节点 | 说明 |
|------|-----------|-----------|------|
| 0x1a | `UU` | `wm8960@1a { compatible = "wlf,wm8960"; }` | 音频编解码器，内核驱动已绑定 |
| 0x20 | `UU` | `gpio@20 { compatible = "ti,tca6416"; }` | GPIO 扩展器，内核驱动已绑定 |
| 0x50 | `50` | （无节点） | EEPROM 存在但没有驱动绑定 |
| 0x76 | — | （无节点） | BME280 接上后会出现，但不会是 `UU`（因为没有设备树节点） |

## 下一步

Phase 2 要做的就是在 `&i2c3` 下面添加 BME280 节点，然后写一个内核驱动让 `compatible` 字符串匹配起来。整个 1476 行文件里，**真正需要改的只有 3-5 行**。
