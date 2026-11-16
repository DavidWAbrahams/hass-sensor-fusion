# Sensor Fusion

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]

Fuse several Home Assistant sensors that measure the same quantity — i.e. three smart rings reporting heart rate, or two thermometers in one room — into a single value. Sensor Fusion watches the input sensors as their values arrive, learns each sensor's slowly drifting bias, and keeps the estimate honest even when one sensor wanders or drops off for hours.

This is better than just averaging sensor values in many cases. For example say your sensors update at different rates; a slow sensor makes the average slower to respond. Or say a thermometer goes offline for an hour then revives; the average jumps around at those moments even though the room temperature was unchanged.

Internally, this is done with the magic of [Kalman filters](https://en.wikipedia.org/wiki/Kalman_filter).

## ✨ Features

- **Drift correction**: learns each sensor's bias over time and removes it from the estimate, with a configurable adaptation horizon
- **No popularity contest**: a sensor that reports every minute does not drown out one that reports every 30 minutes — measurement noise is scaled by each sensor's update rate
- **Coasts through outages**: an unavailable sensor is skipped while the estimate keeps its trend
- **Survives restarts**: the learned filter state is persisted and restored across restarts, reloads and options changes
- **Multiple instances**: set up one fusion per quantity — heart rate here, bedroom temperature there
- **Easy Setup**: configured entirely through the UI, no YAML

**This integration will set up the following platforms.**

| Platform | Description                                                                             |
| -------- | --------------------------------------------------------------------------------------- |
| `sensor` | The fused value, plus one diagnostic bias sensor per input sensor                       |
| `button` | Reset fusion — discards the learned state and re-seeds from the sensors' current values |

## 🚀 Quick Start

### Step 1: Install the Integration

**Prerequisites:** Home Assistant 2026.11 or newer has the Marketplace built in (**Settings** → **Marketplace**). On older versions, install [HACS](https://hacs.xyz/) (Home Assistant Community Store) first.

Click the button below to open the integration in the Marketplace, or in HACS on older versions:

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=DavidWAbrahams&repository=hass-sensor-fusion&category=integration)

Then:

1. Click "Download" to install the integration
2. With HACS (before Home Assistant 2026.11), **restart Home Assistant**. The Marketplace loads it right away.

> [!NOTE]
> The My Home Assistant redirect will first take you to a landing page. Click the button there to open your Home Assistant instance.

<details>
<summary><strong>Manual Installation (Advanced)</strong></summary>

If you prefer not to use the Marketplace or HACS:

1. Download the `custom_components/sensor_fusion/` folder from this repository
2. Copy it to your Home Assistant's `custom_components/` directory
3. Restart Home Assistant

</details>

### Step 2: Add and Configure the Integration

**Important:** You must have installed the integration first (see Step 1), and restarted Home Assistant if Step 1 asked you to.

#### Option 1: One-Click Setup (Quick)

Click the button below to open the configuration dialog:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=sensor_fusion)

Fill in the setup form:

| Setting                   | Example | What it does                                                                                                                 |
| ------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Name**                  | `Rings` | Names this fusion instance; shown as the device name. Empty defaults to "Sensor Fusion".                                     |
| **Input sensors**         | 4 rings | Two or more sensors measuring the same quantity. All must share a unit of measurement.                                       |
| **Signal volatility**     | `2.0`   | How much the quantity moves between sensor updates, in units per square root of a minute. Raise for fast-moving signals.     |
| **Bias adaptation**       | `480`   | Minutes over which a sensor's bias is expected to drift by one maximum-bias step. Lower adapts faster, higher trusts longer. |
| **Maximum expected bias** | `10`    | The largest deviation from the true value a single sensor is expected to develop, in the measurement's unit.                 |

Click **Submit**. The estimate starts immediately from the input sensors' current values.

#### Option 2: Manual Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **"+ Add Integration"**
3. Search for "Sensor Fusion"
4. Follow the same setup steps as Option 1

### Step 3: Adjust Settings (Optional)

After setup, you can adjust options:

1. Go to **Settings** → **Devices & Services**
2. Find your fusion instance
3. Click **Configure** to:
   - Add or remove input sensors — the filter resizes and keeps everything it has learned
   - Retune volatility, bias adaptation and maximum bias — applied to the live filter

### Step 4: Start Using!

The instance appears as one device with:

- **Fused value** — the estimate, in the unit (and device class, if the inputs share a known one) of the input sensors
- **Bias \<sensor\>** (diagnostic) — one per input sensor: how far that sensor reads from the group right now. The biases always sum to zero; a sensor reading consistently high shows a positive bias
- **Reset fusion** — press to discard the learned state and re-seed from the current readings

Use the fused value in dashboards and automations exactly as you would use any sensor entity.

## Tuning Tips

- **Start with the defaults** (volatility 2.0, horizon 480 min, max bias 10) — they suit slowly-measured, slowly-drifting quantities like heart rate from a wearable.
- **The estimate lags a fast-moving signal?** Raise _Signal volatility_. The filter is saying "this signal can't have moved much between updates" when it shouldn't.
- **A sensor swapped out mid-day drags the estimate?** Lower the _Bias adaptation horizon_ so biases are trusted less and relearned faster.
- **Bias entities are noisy or pinned near the maximum?** The _Maximum expected bias_ is the filter's prior on sensor offsets; set it to what you genuinely expect, not lower — the prior also sets the initial measurement noise.
- **Do not put the fused sensor in its own input list.** It measures itself; it adds no information and confuses the bias estimate.

## Troubleshooting

### The fused value is "unknown"

The filter needs at least two usable input readings to seed. Check that at least two input sensors currently hold numeric values.

### A bias entity is "unavailable"

That input sensor is currently unavailable or has left the selection. The fused value is unaffected — it simply coasted through, skipping that source.

### The estimate seems too smooth, or too jumpy

Volatility trades smoothness against responsiveness: higher follows the inputs faster and smooths less. Change it in **Configure**; it applies immediately without losing learned state.

### Debug Logging

```yaml
logger:
  default: info
  logs:
    custom_components.sensor_fusion: debug
```

Diagnostics are available at **Settings** → **Devices & Services** → your instance → **⋯** → **Download diagnostics** (the instance name and config entry data are redacted).

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Made by [@DavidWAbrahams][user_profile]** with the help of 20M tokens run through a locally hosted LLM.

---

[commits-shield]: https://img.shields.io/github/commit-activity/y/DavidWAbrahams/hass-sensor-fusion.svg?style=for-the-badge
[commits]: https://github.com/DavidWAbrahams/hass-sensor-fusion/commits/main
[hacs]: https://www.hacs.xyz/docs/marketplace/
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/DavidWAbrahams/hass-sensor-fusion.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40DavidWAbrahams-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/DavidWAbrahams/hass-sensor-fusion.svg?style=for-the-badge
[releases]: https://github.com/DavidWAbrahams/hass-sensor-fusion/releases
[user_profile]: https://github.com/DavidWAbrahams
