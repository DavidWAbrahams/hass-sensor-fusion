# Getting Started with Sensor Fusion

This guide will help you install and set up the Sensor Fusion custom integration for Home Assistant.

Sensor Fusion combines two or more Home Assistant sensors that measure the same quantity — for example four smart rings reporting heart rate, or two thermometers in one room — into a single estimate that corrects each sensor's slow drift as it learns it.

## Prerequisites

- Home Assistant 2026.10.0 or newer
- At least two existing sensor entities that measure the same quantity in the same unit (for example `sensor.ring_left_heart_rate` and `sensor.ring_right_heart_rate`)

No device, account or network connection is needed beyond what already provides those sensors.

## Installation

### Via the Marketplace (Home Assistant 2026.11 and newer, recommended)

1. Go to **Settings** → **Marketplace**
2. Add this repository as a custom repository: `https://github.com/DavidWAbrahams/hass-sensor-fusion`, category "Integration". The Marketplace asks you to connect a GitHub account for repositories outside its catalog.
3. Open "Sensor Fusion" and click "Download"

A restart is not needed for the first installation; updates and removal ask for one.

### Via HACS (before Home Assistant 2026.11)

1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/DavidWAbrahams/hass-sensor-fusion`
5. Set category to "Integration"
6. Click "Add"
7. Find "Sensor Fusion" in the list and click "Download"
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/DavidWAbrahams/hass-sensor-fusion/releases)
2. Extract the `sensor_fusion` folder from the archive
3. Copy it to `custom_components/sensor_fusion/` in your Home Assistant configuration directory
4. Restart Home Assistant

## Initial Setup

After installation, add the integration:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Sensor Fusion"
4. Fill in the setup form:

   | Setting                   | Default          | What it means                                                                                                                 |
   | ------------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------- |
   | **Name**                  | (empty)          | Names this fusion instance. Empty defaults to "Sensor Fusion".                                                                |
   | **Input sensors**         | —                | Pick at least two sensors measuring the same quantity. All must share a unit of measurement.                                  |
   | **Signal volatility**     | 2.0              | How much the quantity moves between sensor updates, in units per square root of a minute. Higher follows fast changes sooner. |
   | **Bias adaptation**       | 480 (minutes)    | How quickly a sensor's learned bias may change. Lower adapts faster, higher trusts the learned bias longer.                   |
   | **Maximum expected bias** | 10 (in the unit) | The largest deviation from the true value you expect a single sensor to develop.                                              |

5. Click **Submit**

The defaults suit slowly-measured quantities with slow drift, such as heart rate from a wearable. If the estimate feels too smooth for your signal, raise the volatility. Full details of each setting: [Configuration Reference](CONFIGURATION.md).

## What You Get

The integration adds one device named after the instance, with:

- **Fused value** — the estimate, in the unit of the input sensors
- **Bias \<sensor name\>** — one per input sensor, hidden by default (diagnostic): how far that sensor currently reads from the group
- **Reset fusion** — a button that discards everything the filter learned and re-seeds from the sensors' current values

## First Steps

1. Open the new device under **Settings** → **Devices & Services** and watch the **Fused value** — it should sit among the individual sensor readings and update as they do.
2. After a few hours, expand the device's diagnostic entities. A sensor that consistently reads high shows a **positive** bias; the biases always sum to zero, so this tells you which sensor to trust less.
3. Use the fused entity in dashboards and automations exactly like any other sensor.
4. See [EXAMPLES.md](EXAMPLES.md) for automation ideas and tuning walkthroughs.

## Notes

- A sensor that goes unavailable or reports non-numeric values is simply skipped; the estimate coasts on its trend until readings arrive.
- You can create as many fusion instances as you like — one per quantity.
- Everything the filter has learned is saved automatically and restored after restarts, reloads and options changes.
