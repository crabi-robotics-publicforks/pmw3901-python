import struct
import time

import gpiod
import gpiodevice
import spidev
from gpiod.line import Direction, Value

__version__ = "1.0.0"

WAIT = -1

BG_CS_FRONT_BCM = 1  # GPIO 8
BG_CS_BACK_BCM = 0   # GPIO 7

REG_ID = 0x00
REG_DATA_READY = 0x02
REG_MOTION_BURST = 0x16
REG_POWER_UP_RESET = 0x3A
REG_ORIENTATION = 0x5B
REG_RESOLUTION = 0x4E  # PAA5100 only

REG_RAWDATA_GRAB = 0x58
REG_RAWDATA_GRAB_STATUS = 0x59

OUTL = gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE)


class PMW3901:
    _device_name = "PMW3901"

    def __init__(self, spi_port=0, spi_cs=1, spi_cs_gpio=None):
        self.spi_dev = spidev.SpiDev()
        self._spi_cs_gpio = None

        if spi_cs_gpio is not None:
            spi_cs = 0
            self._spi_cs_gpio = gpiodevice.get_pin(spi_cs_gpio, f"{self._device_name}_cs", OUTL)

        self.spi_dev.open(spi_port, spi_cs)
        self.spi_dev.max_speed_hz = 400000

        if spi_cs_gpio is not None:
            try:
                # TODO: Not sure this does anything but break with an OSError?
                self.spi_dev.no_cs = True
            except OSError:
                pass

        if self._spi_cs_gpio:
            self.set_pin(self._spi_cs_gpio, 0)
            time.sleep(0.05)
            self.set_pin(self._spi_cs_gpio, 1)

        self._write(REG_POWER_UP_RESET, 0x5A)
        time.sleep(0.02)
        for offset in range(5):
            self._read(REG_DATA_READY + offset)

        self._secret_sauce()

        product_id, revision = self.get_id()
        if product_id != 0x49 or revision not in (0x00, 0x01):
            raise RuntimeError(f"Invalid Product ID or Revision for PMW3901: 0x{product_id:02x}/0x{revision:02x}")
        # print("Product ID: {}".format(ID.get_product_id()))
        # print("Revision: {}".format(ID.get_revision_id()))

    def set_pin(self, pin, state):
        lines, offset = pin
        lines.set_value(offset, Value.ACTIVE if state else Value.INACTIVE)

    def get_id(self):
        """Get chip ID and revision from PMW3901."""
        return self._read(REG_ID, 2)

    def set_rotation(self, degrees=0):
        """Set orientation of PMW3901 in increments of 90 degrees.

        :param degrees: rotation in multiple of 90 degrees

        """
        if degrees == 0:
            self.set_orientation(invert_x=True, invert_y=True, swap_xy=True)
        elif degrees == 90:
            self.set_orientation(invert_x=False, invert_y=True, swap_xy=False)
        elif degrees == 180:
            self.set_orientation(invert_x=False, invert_y=False, swap_xy=True)
        elif degrees == 270:
            self.set_orientation(invert_x=True, invert_y=False, swap_xy=False)
        else:
            raise TypeError("Degrees must be one of 0, 90, 180 or 270")

    def set_orientation(self, invert_x=True, invert_y=True, swap_xy=True):
        """Set orientation of PMW3901 manually.

        Swapping is performed before flipping.

        :param invert_x: invert the X axis
        :param invert_y: invert the Y axis
        :param swap_xy: swap the X/Y axes

        """
        value = 0
        if swap_xy:
            value |= 0b10000000
        if invert_y:
            value |= 0b01000000
        if invert_x:
            value |= 0b00100000
        self._write(REG_ORIENTATION, value)

    def get_motion(self, timeout=5):
        """Get motion data from PMW3901 using burst read.

        Reads 12 bytes sequentially from the PMW3901 and validates
        motion data against the SQUAL and Shutter_Upper values.

        Returns Delta X and Delta Y indicating 2d flow direction
        and magnitude.

        :param timeout: Timeout in seconds

        """
        t_start = time.time()
        while time.time() - t_start < timeout:
            if self._spi_cs_gpio:
                self.set_pin(self._spi_cs_gpio, 0)
            data = self.spi_dev.xfer2([REG_MOTION_BURST] + [0 for x in range(12)])
            if self._spi_cs_gpio:
                self.set_pin(self._spi_cs_gpio, 1)
            (_, dr, obs,
             x, y, quality,
             raw_sum, raw_max, raw_min,
             shutter_upper,
             shutter_lower) = struct.unpack("<BBBhhBBBBBB", bytearray(data))

            if dr & 0b10000000 and not (quality < 0x19 and shutter_upper == 0x1F):
                return x, y

            time.sleep(0.001) # reducing the sleep time to get data faster

        raise RuntimeError("Timed out waiting for motion data.")

    def get_motion_slow(self, timeout=5):
        """Get motion data from PMW3901.

        Returns Delta X and Delta Y indicating 2d flow direction
        and magnitude.

        :param timeout: Timeout in seconds

        """
        t_start = time.time()
        while time.time() - t_start < timeout:
            data = self._read(REG_DATA_READY, 5)
            dr, x, y = struct.unpack("<Bhh", bytearray(data))
            if dr & 0b10000000:
                return x, y
            time.sleep(0.001)

        raise RuntimeError("Timed out waiting for motion data.")

    def _write(self, register, value):
        if self._spi_cs_gpio:
                self.set_pin(self._spi_cs_gpio, 0)
        self.spi_dev.xfer2([register | 0x80, value])
        if self._spi_cs_gpio:
                self.set_pin(self._spi_cs_gpio, 1)

    def _read(self, register, length=1):
        result = []
        for x in range(length):
            if self._spi_cs_gpio:
                self.set_pin(self._spi_cs_gpio, 0)
            value = self.spi_dev.xfer2([register + x, 0])
            if self._spi_cs_gpio:
                self.set_pin(self._spi_cs_gpio, 1)
            result.append(value[1])

        if length == 1:
            return result[0]
        else:
            return result

    def _bulk_write(self, data):
        for x in range(0, len(data), 2):
            register, value = data[x : x + 2]
            if register == WAIT:
                # print("Sleeping for: {:02d}ms".format(value))
                time.sleep(value / 1000)
            else:
                # print("Writing: {:02x} to {:02x}".format(register, value))
                self._write(register, value)

    def _secret_sauce(self):
        """Write the secret sauce registers.

        Don't ask what these do, the datasheet refuses to explain.

        They are some proprietary calibration magic.

        """
        self._bulk_write([
            0x7F, 0x00,
            0x55, 0x01,
            0x50, 0x07,

            0x7F, 0x0E,
            0x43, 0x10
        ])
        if self._read(0x67) & 0b10000000:
            self._write(0x48, 0x04)
        else:
            self._write(0x48, 0x02)
        self._bulk_write([
            0x7F, 0x00,
            0x51, 0x7B,

            0x50, 0x00,
            0x55, 0x00,
            0x7F, 0x0E
        ])
        if self._read(0x73) == 0x00:
            c1 = self._read(0x70)
            c2 = self._read(0x71)
            if c1 <= 28:
                c1 += 14
            if c1 > 28:
                c1 += 11
            c1 = max(0, min(0x3F, c1))
            c2 = (c2 * 45) // 100
            self._bulk_write([
                0x7F, 0x00,
                0x61, 0xAD,
                0x51, 0x70,
                0x7F, 0x0E
            ])
            self._write(0x70, c1)
            self._write(0x71, c2)
        self._bulk_write([
            0x7F, 0x00,
            0x61, 0xAD,
            0x7F, 0x03,
            0x40, 0x00,
            0x7F, 0x05,

            0x41, 0xB3,
            0x43, 0xF1,
            0x45, 0x14,
            0x5B, 0x32,
            0x5F, 0x34,
            0x7B, 0x08,
            0x7F, 0x06,
            0x44, 0x1B,
            0x40, 0xBF,
            0x4E, 0x3F,
            0x7F, 0x08,
            0x65, 0x20,
            0x6A, 0x18,

            0x7F, 0x09,
            0x4F, 0xAF,
            0x5F, 0x40,
            0x48, 0x80,
            0x49, 0x80,

            0x57, 0x77,
            0x60, 0x78,
            0x61, 0x78,
            0x62, 0x08,
            0x63, 0x50,
            0x7F, 0x0A,
            0x45, 0x60,
            0x7F, 0x00,
            0x4D, 0x11,

            0x55, 0x80,
            0x74, 0x21,
            0x75, 0x1F,
            0x4A, 0x78,
            0x4B, 0x78,

            0x44, 0x08,
            0x45, 0x50,
            0x64, 0xFF,
            0x65, 0x1F,
            0x7F, 0x14,
            0x65, 0x67,
            0x66, 0x08,
            0x63, 0x70,
            0x7F, 0x15,
            0x48, 0x48,
            0x7F, 0x07,
            0x41, 0x0D,
            0x43, 0x14,

            0x4B, 0x0E,
            0x45, 0x0F,
            0x44, 0x42,
            0x4C, 0x80,
            0x7F, 0x10,

            0x5B, 0x02,
            0x7F, 0x07,
            0x40, 0x41,
            0x70, 0x00,
            WAIT, 0x0A,  # Sleep for 10ms

            0x32, 0x44,
            0x7F, 0x07,
            0x40, 0x40,
            0x7F, 0x06,
            0x62, 0xF0,
            0x63, 0x00,
            0x7F, 0x0D,
            0x48, 0xC0,
            0x6F, 0xD5,
            0x7F, 0x00,

            0x5B, 0xA0,
            0x4E, 0xA8,
            0x5A, 0x50,
            0x40, 0x80,
            WAIT, 0xF0,

            0x7F, 0x14,  # Enable LED_N pulsing
            0x6F, 0x1C,
            0x7F, 0x00
        ])

    def frame_capture(self, timeout=10.0):
        """Capture a raw data frame.

        Warning: This is *very* slow and of limited usefulness.

        """
        self._bulk_write([
            0x7F, 0x07,
            0x4C, 0x00,
            0x7F, 0x08,
            0x6A, 0x38,
            0x7F, 0x00,
            0x55, 0x04,
            0x40, 0x80,
            0x4D, 0x11,

            WAIT, 0x0A,

            0x7F, 0x00,
            0x58, 0xFF
        ])

        t_start = time.time()

        while True:
            status = self._read(REG_RAWDATA_GRAB_STATUS)
            if status & 0b11000000:
                break

            if time.time() - t_start > timeout:
                raise RuntimeError("Frame capture init timed out")

        self._write(REG_RAWDATA_GRAB, 0x00)

        RAW_DATA_LEN = 1225

        t_start = time.time()
        raw_data = [0 for _ in range(RAW_DATA_LEN)]
        x = 0

        while True:
            data = self._read(REG_RAWDATA_GRAB)
            if data & 0b11000000 == 0b01000000:  # Upper 6-bits
                raw_data[x] &= ~0b11111100
                raw_data[x] |= (data & 0b00111111) << 2         # Held in 5:0
            if data & 0b11000000 == 0b10000000:  # Lower 2-bits
                raw_data[x] &= ~0b00000011
                raw_data[x] |= (data & 0b00001100) >> 2   # Held in 3:2
                x += 1
            if x == RAW_DATA_LEN:
                return raw_data
            if time.time() - t_start > timeout:
                raise RuntimeError(f"Raw data capture timeout, got {x} values")

        return None


class PAA5100(PMW3901):
    _device_name = "PAA5100"

    def _secret_sauce(self):
        """Write the secret sauce registers for the PAA5100.

        Don't ask what these do, we'd have to make you walk the plank.

        These are some proprietary calibration magic.

        I hate this as much as you do, dear reader.

        """
        self._bulk_write([
            0x7F, 0x00,
            0x55, 0x01,
            0x50, 0x07,

            0x7F, 0x0E,
            0x43, 0x10
        ])
        if self._read(0x67) & 0b10000000:
            self._write(0x48, 0x04)
        else:
            self._write(0x48, 0x02)
        self._bulk_write([
            0x7F, 0x00,
            0x51, 0x7B,
            0x50, 0x00,
            0x55, 0x00,
            0x7F, 0x0E
        ])
        if self._read(0x73) == 0x00:
            c1 = self._read(0x70)
            c2 = self._read(0x71)
            if c1 <= 28:
                c1 += 14
            if c1 > 28:
                c1 += 11
            c1 = max(0, min(0x3F, c1))
            c2 = (c2 * 45) // 100
            self._bulk_write([
                0x7F, 0x00,
                0x61, 0xAD,
                0x51, 0x70,
                0x7F, 0x0E
            ])
            self._write(0x70, c1)
            self._write(0x71, c2)
        self._bulk_write([
            0x7F, 0x00,
            0x61, 0xAD,

            0x7F, 0x03,
            0x40, 0x00,

            0x7F, 0x05,
            0x41, 0xB3,
            0x43, 0xF1,
            0x45, 0x14,

            0x5F, 0x34,
            0x7B, 0x08,
            0x5E, 0x34,
            0x5B, 0x11,
            0x6D, 0x11,
            0x45, 0x17,
            0x70, 0xE5,
            0x71, 0xE5,

            0x7F, 0x06,
            0x44, 0x1B,
            0x40, 0xBF,
            0x4E, 0x3F,

            0x7F, 0x08,
            0x66, 0x44,
            0x65, 0x20,
            0x6A, 0x3A,
            0x61, 0x05,
            0x62, 0x05,

            0x7F, 0x09,
            0x4F, 0xAF,
            0x5F, 0x40,
            0x48, 0x80,
            0x49, 0x80,
            0x57, 0x77,
            0x60, 0x78,
            0x61, 0x78,
            0x62, 0x08,
            0x63, 0x50,

            0x7F, 0x0A,
            0x45, 0x60,

            0x7F, 0x00,
            0x4D, 0x11,
            0x55, 0x80,
            0x74, 0x21,
            0x75, 0x1F,
            0x4A, 0x78,
            0x4B, 0x78,
            0x44, 0x08,

            0x45, 0x50,
            0x64, 0xFF,
            0x65, 0x1F,

            0x7F, 0x14,
            0x65, 0x67,
            0x66, 0x08,
            0x63, 0x70,
            0x6F, 0x1C,

            0x7F, 0x15,
            0x48, 0x48,

            0x7F, 0x07,
            0x41, 0x0D,
            0x43, 0x14,
            0x4B, 0x0E,
            0x45, 0x0F,
            0x44, 0x42,
            0x4C, 0x80,

            0x7F, 0x10,
            0x5B, 0x02,

            0x7F, 0x07,
            0x40, 0x41,

            WAIT, 0x0A,  # Wait 10ms

            0x7F, 0x00,
            0x32, 0x00,

            0x7F, 0x07,
            0x40, 0x40,

            0x7F, 0x06,
            0x68, 0xF0,
            0x69, 0x00,

            0x7F, 0x0D,
            0x48, 0xC0,
            0x6F, 0xD5,

            0x7F, 0x00,
            0x5B, 0xA0,
            0x4E, 0xA8,
            0x5A, 0x90,
            0x40, 0x80,
            0x73, 0x1F,

            WAIT, 0x0A,  # Wait 10ms

            0x73, 0x00
        ])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rotation", type=int,
                        default=0, choices=[0, 90, 180, 270],
                        help="Rotation of sensor in degrees.", )
    args = parser.parse_args()
    flo = PMW3901(spi_port=0, spi_cs_gpio=BG_CS_FRONT_BCM)
    flo.set_rotation(args.rotation)
    tx = 0
    ty = 0
    try:
        while True:
            try:
                x, y = flo.get_motion()
            except RuntimeError:
                continue
            tx += x
            ty += y
            print(f"Motion: {x:03d} {y:03d} x: {tx:03d} y {ty:03d}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
