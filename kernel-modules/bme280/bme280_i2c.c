// SPDX-License-Identifier: GPL-2.0
/*
 * bme280_i2c.c — I2C client driver for Bosch BME280 sensor
 *
 * Demonstrates the Linux I2C subsystem driver model:
 *   1. Probe/remove lifecycle tied to device tree matching
 *   2. I2C register read/write via smbus API
 *   3. Sysfs attribute interface (read sensor data from userspace)
 *   4. Device tree compatible string matching
 *
 * On the i.MX8MP EVK, I2C buses are:
 *   I2C1 (i2c@30a20000) — PMIC, camera (OV5640 at 0x3c)
 *   I2C2 (i2c@30a30000) — HDMI
 *   I2C3 (i2c@30a40000) — available on expansion header
 *
 * Device tree binding (add to your overlay):
 *
 *   &i2c3 {
 *       bme280: bme280@76 {
 *           compatible = "bosch,bme280";
 *           reg = <0x76>;
 *       };
 *   };
 *
 * Usage:
 *   insmod bme280_i2c.ko
 *   cat /sys/bus/i2c/devices/<bus>-0076/chip_id      # should be 0x60
 *   cat /sys/bus/i2c/devices/<bus>-0076/temperature   # raw temp register
 */

#include <linux/init.h>
#include <linux/module.h>
#include <linux/i2c.h>       /* i2c_client, i2c_driver, i2c_smbus_* */
#include <linux/device.h>    /* DEVICE_ATTR, sysfs */

/* BME280 register map (subset — see Bosch datasheet BST-BME280-DS002) */
#define BME280_REG_CHIP_ID    0xD0   /* reads 0x60 for BME280, 0x58 for BMP280 */
#define BME280_REG_RESET      0xE0   /* write 0xB6 to soft-reset */
#define BME280_REG_CTRL_HUM   0xF2   /* humidity oversampling */
#define BME280_REG_STATUS     0xF3   /* measuring / im_update bits */
#define BME280_REG_CTRL_MEAS  0xF4   /* temp/press oversampling + mode */
#define BME280_REG_TEMP_MSB   0xFA   /* temperature data [19:12] */

#define BME280_CHIP_ID        0x60

/*
 * Per-device private data — allocated in probe(), freed in remove().
 *
 * In production drivers, this holds calibration data, DMA buffers,
 * IRQ numbers, regmap pointers, etc. Here we keep it minimal.
 */
struct bme280_data {
	struct i2c_client *client;
	u8 chip_id;
};

/*
 * Sysfs attribute: chip_id
 *
 * Reading /sys/bus/i2c/devices/.../chip_id returns the BME280 chip ID.
 * DEVICE_ATTR_RO creates a read-only attribute with show function.
 *
 *   cat /sys/bus/i2c/devices/2-0076/chip_id → "0x60"
 */
static ssize_t chip_id_show(struct device *dev, struct device_attribute *attr,
			    char *buf)
{
	struct bme280_data *data = dev_get_drvdata(dev);
	return sysfs_emit(buf, "0x%02x\n", data->chip_id);
}
static DEVICE_ATTR_RO(chip_id);

/*
 * Sysfs attribute: temperature (raw register value)
 *
 * In a production driver you'd apply the BME280 compensation formula
 * (involves calibration registers 0x88–0x9F). Here we just read raw.
 */
static ssize_t temperature_show(struct device *dev,
				struct device_attribute *attr, char *buf)
{
	struct bme280_data *data = dev_get_drvdata(dev);
	int msb, lsb, xlsb;
	s32 raw;

	msb  = i2c_smbus_read_byte_data(data->client, BME280_REG_TEMP_MSB);
	lsb  = i2c_smbus_read_byte_data(data->client, BME280_REG_TEMP_MSB + 1);
	xlsb = i2c_smbus_read_byte_data(data->client, BME280_REG_TEMP_MSB + 2);

	if (msb < 0 || lsb < 0 || xlsb < 0)
		return -EIO;

	/* BME280 temperature is 20-bit unsigned, stored across 3 registers */
	raw = ((s32)msb << 12) | ((s32)lsb << 4) | ((s32)xlsb >> 4);
	return sysfs_emit(buf, "%d\n", raw);
}
static DEVICE_ATTR_RO(temperature);

static struct attribute *bme280_attrs[] = {
	&dev_attr_chip_id.attr,
	&dev_attr_temperature.attr,
	NULL,
};
ATTRIBUTE_GROUPS(bme280);

/*
 * probe() — called when the kernel finds a matching device.
 *
 * Matching happens via compatible string in device tree:
 *   Device tree: compatible = "bosch,bme280"
 *   Driver:      { .compatible = "bosch,bme280" } in of_match_table
 *
 * The kernel's I2C core has already set up the i2c_client with the
 * correct bus and address. We just need to verify and initialize.
 *
 * This is the ENTRY POINT for device lifecycle, analogous to a
 * constructor in OOP.
 */
static int bme280_probe(struct i2c_client *client)
{
	struct bme280_data *data;
	int chip_id;

	/* Read and verify chip ID */
	chip_id = i2c_smbus_read_byte_data(client, BME280_REG_CHIP_ID);
	if (chip_id < 0) {
		dev_err(&client->dev, "failed to read chip ID: %d\n", chip_id);
		return chip_id;
	}

	if (chip_id != BME280_CHIP_ID) {
		dev_err(&client->dev, "unexpected chip ID: 0x%02x (expected 0x%02x)\n",
			chip_id, BME280_CHIP_ID);
		return -ENODEV;
	}

	/*
	 * devm_kzalloc — device-managed allocation.
	 * Memory is automatically freed when the device is removed.
	 * No need for explicit kfree() in remove(). The "devm_" prefix
	 * means "device managed" — the kernel tracks and cleans up.
	 */
	data = devm_kzalloc(&client->dev, sizeof(*data), GFP_KERNEL);
	if (!data)
		return -ENOMEM;

	data->client = client;
	data->chip_id = chip_id;

	/* Store private data — retrievable via dev_get_drvdata() */
	dev_set_drvdata(&client->dev, data);

	/*
	 * Configure sensor: normal mode, 1x oversampling for temp/press/hum
	 * Ctrl_hum must be written BEFORE ctrl_meas (per datasheet §5.4.3)
	 */
	i2c_smbus_write_byte_data(client, BME280_REG_CTRL_HUM, 0x01);
	i2c_smbus_write_byte_data(client, BME280_REG_CTRL_MEAS, 0x27);

	dev_info(&client->dev, "BME280 detected (chip_id=0x%02x) on %s addr 0x%02x\n",
		 chip_id, client->adapter->name, client->addr);
	return 0;
}

/*
 * remove() — called when device is unbound (rmmod, device tree overlay
 *            removal, or system shutdown).
 *
 * With devm_kzalloc, we don't need to free memory manually.
 * In a real driver, you'd stop DMA, disable IRQs, power down HW.
 */
static void bme280_remove(struct i2c_client *client)
{
	/* Put sensor to sleep mode (mode bits = 00) */
	i2c_smbus_write_byte_data(client, BME280_REG_CTRL_MEAS, 0x00);
	dev_info(&client->dev, "BME280 driver removed\n");
}

/*
 * Device tree match table — this is how the kernel knows which
 * devices this driver supports. When a device tree node has
 * compatible = "bosch,bme280", this driver's probe() is called.
 */
static const struct of_device_id bme280_of_match[] = {
	{ .compatible = "bosch,bme280" },
	{ .compatible = "bosch,bmp280" },  /* register-compatible subset */
	{ }  /* sentinel — marks end of table */
};
MODULE_DEVICE_TABLE(of, bme280_of_match);

/* I2C device ID table — for non-device-tree platforms (legacy) */
static const struct i2c_device_id bme280_id[] = {
	{ "bme280" },
	{ "bmp280" },
	{ }
};
MODULE_DEVICE_TABLE(i2c, bme280_id);

/*
 * i2c_driver — the driver registration structure.
 *
 * The I2C core uses this to:
 *   1. Match against device tree nodes (via of_match_table)
 *   2. Call probe() when a match is found
 *   3. Call remove() on unbind
 */
static struct i2c_driver bme280_driver = {
	.driver = {
		.name           = "bme280",
		.of_match_table = bme280_of_match,
		.dev_groups     = bme280_groups,
	},
	.probe    = bme280_probe,
	.remove   = bme280_remove,
	.id_table = bme280_id,
};

/*
 * module_i2c_driver() — one-line macro that generates init/exit boilerplate.
 * Expands to module_init() + module_exit() with i2c_add/del_driver calls.
 * Equivalent to writing hello.c's init/exit but for I2C specifically.
 */
module_i2c_driver(bme280_driver);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("NTU M266 Embedded Linux");
MODULE_DESCRIPTION("BME280 I2C sensor driver for i.MX8MP EVK");
MODULE_VERSION("1.0");
