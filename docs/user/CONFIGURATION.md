# Configuration Reference

This document describes all configuration options and settings available in the Sensor Fusion custom integration.

Sensor Fusion is configured entirely through the Home Assistant UI. There is no YAML configuration.

## Integration Configuration

### Initial Setup (Config Flow)

These options are set when you add an instance under **Settings** → **Devices & Services** → **+ Add Integration** → "Sensor Fusion".

| Option                    | Type        | Required | Default         | Range       | Description                                                                                                                                   |
| ------------------------- | ----------- | -------- | --------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **Name**                  | string      | No       | `Sensor Fusion` | —           | Names this fusion instance and its device. Leave empty for the default.                                                                       |
| **Input sensors**         | sensor list | Yes      | —               | at least 2  | The sensors to fuse. They must share the same unit of measurement and device class (if set).                                                  |
| **Signal volatility**     | number      | No       | `2.0`           | 0.01 – 1000 | How much the measured quantity moves between sensor updates, in units per √minute. Higher makes the estimate follow changes faster.           |
| **Bias adaptation**       | number      | No       | `480` (minutes) | 1 – 43200   | Minutes over which a sensor's bias is expected to drift by one maximum-bias step. Lower adapts faster, higher trusts the learned bias longer. |
| **Maximum expected bias** | number      | No       | `10`            | 0.01 – 1000 | The largest deviation from the true value a single sensor is expected to develop, in the measurement's unit.                                  |

### Validation

The form rejects a selection with:

- **"Select at least two different sensors to fuse."** — fewer than two distinct sensors were chosen.
- **"The selected sensors must share the same unit of measurement and device class."** — mixing, say, `°C` and `°F` or a heart-rate and a temperature sensor is refused up front.

### Multiple Instances

Each setup creates an independent instance with its own filter, storage and device. Create one per quantity you want to fuse (heart rate, bedroom temperature, …). An input sensor may appear in more than one instance.

### Options (Configure)

After setup, **Settings** → **Devices & Services** → your instance → **Configure** shows the same form minus the name:

- **Input sensors** — add or remove sensors. The filter resizes: a new sensor starts at zero bias with full prior uncertainty and learns from here; a removed sensor is forgotten. The estimate continues across the change, and the entry reloads so entities follow.
- **Signal volatility / Bias adaptation / Maximum expected bias** — retuning is applied to the live filter without discarding anything it learned.

The name is fixed after setup; rename the device via the device's settings if needed.

## Entities

Each instance provides:

| Entity              | Platform | Category   | Description                                                                                                                                      |
| ------------------- | -------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Fused value**     | sensor   | (normal)   | The Kalman estimate. Unit and device class are inherited from the input sensors when they share them. State class `measurement`, two decimals.   |
| **Bias \<sensor\>** | sensor   | diagnostic | One per input sensor: the deviation the filter has learned for that sensor. Biases sum to zero, so they are relative to the group, not absolute. |
| **Reset fusion**    | button   | (normal)   | Discards the learned state and re-seeds from the input sensors' current values.                                                                  |

Bias entities and their availability: a bias entity is `unavailable` exactly while its input sensor is; the fused value is unaffected and coasts.

## Behaviour Reference

- **Event-driven**: the filter runs one cycle per input-sensor state change. There is no update interval; nothing is polled.
- **Coasting**: while no input reports, the estimate holds and extrapolates along its learned trend, with uncertainty growing. A trend left over from before an outage is kept.
- **Update-rate fairness**: measurement noise is inflated for sensors that report more often than the group median, so a chatty sensor cannot dominate a slow one.
- **Persistence**: the filter state is saved at most every five minutes (and on shutdown/reload) under **Settings** → system storage; it is restored on restart and resized on options changes.
- **Identifiability**: because the biases are constrained to sum to zero, an offset shared by _every_ input is absorbed into the fused value rather than shown as bias. This is expected: with no unbiased reference there is nothing to measure the common offset against.

## Troubleshooting

| Symptom                                        | Likely cause and fix                                                                                                          |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Fused value is `unknown`                       | Fewer than two inputs currently hold numeric readings. Check the input sensors.                                               |
| Estimate lags real changes                     | Raise **Signal volatility**.                                                                                                  |
| Estimate is twitchy                            | Lower **Signal volatility**, and check whether one input is noisy — its bias entity shows if the filter is fighting it.       |
| A sensor's bias sticks at the maximum          | Raise **Maximum expected bias**, or check that sensor — it may genuinely be out of line.                                      |
| A new sensor drags the estimate                | Normal for the first while: it starts at zero bias and must be learned. Lower the **Bias adaptation** minutes to speed it up. |
| After swapping hardware the old offset lingers | Press **Reset fusion** to discard learned state.                                                                              |

### Debug Logging

```yaml
logger:
  default: info
  logs:
    custom_components.sensor_fusion: debug
```

### Diagnostics

**Settings** → **Devices & Services** → your instance → **⋯** → **Download diagnostics** includes the filter state (fused value, biases, per-sensor timing and noise statistics, last update success). The instance name and config entry data are redacted automatically.
