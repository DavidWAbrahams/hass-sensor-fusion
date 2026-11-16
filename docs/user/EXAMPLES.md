# Sensor Fusion Examples

Practical setups and automation ideas for Sensor Fusion.

## Fusing Four Smart Rings' Heart Rate

The motivating case: four rings each report a heart rate every few minutes, each drifting a little differently over days.

1. Set up a Sensor Fusion instance named `Rings` with all four `sensor.*_heart_rate` entities.
2. Keep the defaults (volatility 2.0, bias adaptation 480 min, max bias 10 bpm) for a first week.
3. Watch the bias entities: after a day or two, a consistently-high ring shows a positive bias and the fused value is no longer dragged by it.

The fused sensor works with anything a heart-rate sensor works with — cards, thresholds, and Home Assistant's own health-related automations.

### Dashboard Card

```yaml
type: sensor
entity: sensor.rings_fused_value
name: Heart rate (fused)
graph: line
detail: 2
```

## Alert on a Diverging Sensor

Use the bias entities as a calibration watchdog — a bias that runs away usually means a sensor needs attention (worn loosely, low battery, needs cleaning):

```yaml
automation:
  - alias: "Ring sensor drifting"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.rings_bias_ring_alpha
        above: 6
        for: "01:00:00"
    actions:
      - action: notify.phone
        data:
          message: "Ring Alpha reads 6+ bpm off the fused value for an hour — check the fit."
```

(Bias entity friendly names are `Bias <sensor name>`; use the entity picker to find the exact entity ID.)

## Bedroom Temperature From Two Thermometers

Two temperature sensors rarely report at once and each has its own offset from placement (in sunlight, near the window):

- Fuse them into `sensor.bedroom_temperature`.
- Lower **Signal volatility** to `0.1` °C/√min — room temperature barely moves between readings — so the estimate is very smooth.
- The bias entities tell you which thermometer sits in the sun.

## Coasting Through an Outage

A BLE proxy drops, and the ring sensors go `unavailable` for twenty minutes:

- The fused value keeps updating along its learned trend instead of going stale or unknown.
- Only the affected **Bias** entities show `unavailable`.
- When readings resume, they are accepted against the grown uncertainty and the estimate blends back in.

Nothing to configure — this is what happens by default.

## Automating a Reset After Hardware Changes

If a replaced or re-calibrated sensor keeps an old learned bias, reset the instance:

```yaml
automation:
  - alias: "Re-seed fusion after battery swap"
    triggers:
      - trigger: state
        entity_id: binary_sensor.ring_beta_charging
        to: "on"
    conditions:
      - condition: numeric_state
        entity_id: sensor.ring_beta_battery_level
        below: 5
    actions:
      - action: button.press
        target:
          entity_id: button.rings_reset_fusion
```

Pressing **Reset fusion** re-seeds from whatever the inputs read right now, so trigger it when the sensors are in a known-good state.

## Comparing an Input Against the Fused Value

A template-based sanity display of how far one raw sensor deviates right now:

```yaml
template:
  - sensor:
      - name: "Ring Alpha raw deviation"
        unit_of_measurement: "bpm"
        state: >
          {{ (states('sensor.ring_alpha_heart_rate') | float(0)
              - states('sensor.rings_fused_value') | float(0)) | round(1) }}
```

This differs from the bias entity (which is the filter's smoothed estimate) and is useful for spotting a sensor that jumped _today_.

## Tuning Walkthrough

| Observation                                             | Try                                                                           |
| ------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Estimate is a step behind a fast-rising value           | Raise **Signal volatility** (e.g. 2.0 → 5.0)                                  |
| Estimate visibly jitters with every single reading      | Lower **Signal volatility**                                                   |
| A sensor that was recalibrated drags the value for days | Lower **Bias adaptation** minutes, or press **Reset fusion**                  |
| Bias entities hover at the configured maximum           | **Maximum expected bias** is too low for these sensors                        |
| Estimate barely moves even when all sensors agree       | Too few updates yet — the filter needs to have seen each sensor at least once |

Change one setting at a time and give it a few update cycles; the options apply live without losing learned state, so tuning is safe to experiment with.
