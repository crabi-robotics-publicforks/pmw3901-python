# PMW3901 / PAA5100JE 2-Dimensional Optical Flow Sensor

[![Build Status](https://img.shields.io/github/actions/workflow/status/pimoroni/pmw3901-python/test.yml?branch=main)](https://github.com/pimoroni/pmw3901-python/actions/workflows/test.yml)
[![Coverage Status](https://coveralls.io/repos/github/pimoroni/pmw3901-python/badge.svg?branch=main)](https://coveralls.io/github/pimoroni/pmw3901-python?branch=main)
[![PyPi Package](https://img.shields.io/pypi/v/pmw3901.svg)](https://pypi.python.org/pypi/pmw3901)
[![Python Versions](https://img.shields.io/pypi/pyversions/pmw3901.svg)](https://pypi.python.org/pypi/pmw3901)


# Installing

### From GitHub:

Stable library from GitHub:

* `git clone git@github.com:crabi-robotics-publicforks/pmw3901-python.git`
* `cd pmw3901-python`
* `./install.sh`

**Note** Libraries will be installed in the "pimoroni" virtual environment,
you will need to activate it to run examples:

```
source ~/.virtualenvs/pimoroni/bin/activate
```

# Permission Requirements : 
Check if your SPI is enabled by your harware interface 
One can check this by doing:
```
 ls /dev | grep spi*
```
One will find : spidev0.0  spidev0.1 in the output 

Before running your program that interacts with SPI devices, you can manually change the permissions using the following commands:

```bash
sudo chmod +666 /dev/spidev0.0
sudo chmod +666 /dev/spidev0.1
```

Permanent Access (Recommended)

To ensure the permissions are set correctly every time the system boots, create a custom udev rule.

Steps:

Create a new udev rules file:

```bash
sudo nano /etc/udev/rules.d/99-spidev.rules
```

Add the following lines to the file:
```bash
KERNEL=="spidev0.0", MODE="0666"
KERNEL=="spidev0.1", MODE="0666"
```
Reload udev rules and trigger changes:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```
Reboot and verify permissions:
After rebooting, check the device permissions using:
```bash
ls -l /dev/spidev0.*
```
You should see output like:
```bash
crw-rw-rw- 1 root root 153, 0 Jun 11 10:00 /dev/spidev0.0
crw-rw-rw- 1 root root 153, 1 Jun 11 10:00 /dev/spidev0.1
```

# Usage

The PAA5100JE has a slightly different init routine to the PMW3901, you
should use the class provided to ensure it's set up correctly:

```
from pmw3901 import PAA5100
```

And for the PMW3901, continue using the old class:

```
from pmw3901 import PMW3901
```

The example `motion.py` demonstrates setting up either sensor, and accepts
a `--board` argument to specify which you'd like to use.

```bash
python3 motion.py --board paa5100 
```

# Alternate SPI Chip-Select

This library supports specifying a GPIO pin for chip select, you might want
to first first disable SPI chip select support by adding the following
to `/boot/firmware/config.txt`:

```
dtoverlay=spi0-0cs
```

Then use the library with:

```python
from pmw3901 import PAA5100
sensor = PAA5100(spi_cs_gpio=<gpio_pin>)
```