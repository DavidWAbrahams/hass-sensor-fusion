# Plan: Sensor Fusion — event-driven constrained Kalman filter helper integration

## Goal

Users pick 2+ same-kind sensor entities and get one fused sensor (plus per-sensor learned-bias
diagnostics) that tracks the true value, learns each sensor's drifting bias under a zero-sum
constraint, survives restarts and sensor outages, and never lets a fast-polling sensor dominate.

## Current state

- Repository is the **uninitialised blueprint** (`initialize.sh` present) — domain/class prefix are
  still `sensor_fusion` / `SensorFusion` placeholders. `initialize.sh` must run
  first; it would overwrite integration code written beforehand.
- `custom_components/sensor_fusion/` ships the demo: `api/` HTTP client, polling
  `coordinator/base.py`, seven example platforms, credentials config flow, example
  `service_actions/` + `services.yaml`.
- `tests/` cover only the demo.

## Approach

- **Produce, not fetch**: values come from existing HA entities → delete `api/`,
  `integration_type: helper`, `iot_class: calculated`. No credentials, no reauth.
- **Event-driven core**: subscribe with `async_track_state_change_event` for all input entities.
  Each valid numeric state change = predict by Δt + single-sensor update, exactly once per event.
  No polling timer.
- **Pure-math engine separated from HA**: a dependency-light Kalman module (numpy — HA core ships
  it, so no new manifest requirement) holds the state vector `x = [y, ẏ, b₁ … b_{N-1}]`, covariance
  `P`, `F(Δt)`/`Q(Δt)` construction, per-sensor `H_i`/`R_i`, the N-th sensor's zero-sum `H`,
  resize/re-centre, and (de)serialisation. Fully unit-testable without `hass`.
- **Coordinator stays the hub** (blueprint layering entities → coordinator → source preserved):
  the coordinator owns the engine, the event listener, the per-sensor inter-arrival EMA that scales
  `R_i` (fast-sensor de-dominance), and persistence. Entities read `coordinator.data`.
- **Persistence via `helpers.storage.Store`** keyed per config entry — not `RestoreEntity`: the
  state vector belongs to the entry, not an entity, and a Store survives reloads and updates.
  x, P, per-sensor timing stats, format version. Save debounced + on unload.
- **Config flow**: one step — name + multi `sensor` entity selector (min 2) + the three high-level
  filter parameters. All functional settings live in `entry.options`; changes reload the entry,
  which re-loads the Store and resizes x/P (new biases 0 with `P_bias(0)` from Max Expected Bias,
  existing re-centred to keep Σb=0). No `unique_id` (a helper; multiple instances allowed).
- **Physical → filter mapping** (translation table lives in the engine, documented):
  - Signal Volatility σ*y (units/√min) → `Q_y`, `Q*ẏ` (continuous white-noise-acceleration model).
  - Bias Adaptation Horizon τ_bias → `Q_bias = σ_drift²·Δt/τ_bias`, σ_drift from Max Expected Bias.
  - Max Expected Bias → `P_bias(0)` and the drift scale.
  - Sensor update interval EMA → `R_i` inflation so k rapid samples ≈ 1 independent sample.

**Seams fixed by this plan** (check these now): engine module API (`step(dt, sensor_index, z)`,
`resize()`, `to_dict()/from_dict()`); `coordinator.data` shape (dataclass: fused value, per-sensor
bias/variance/availability, input count); unique IDs `{entry_id}_fusion`,
`{entry_id}_bias_{sha1(entity_id)[:8]}`; Store key `sensor_fusion_state.{entry_id}`; config
options keys in `const.py`.

**Not doing in v1** (deliberate): per-sensor R/volatility overrides, chi-squared outlier gating,
discovery, device triggers/conditions, non-numeric or mixed-unit fusion, rate-limited saving.
Recorded as future work, not silent omissions.

## Phases

### Phase 0 — Initialise the blueprint

- **Files:** repository-wide (`initialize.sh`, then it deletes itself).
- **Changes:** run `./initialize.sh --domain … --title … --namespace … --repo … --force`
  unattended (values: open question to developer). Verify placeholders gone, template suite green.
- **Verification:** `script/test`, `rg sensor_fusion` → nothing.
- **Independently shippable:** yes

### Phase 1 — Kalman engine (risky math first)

- **Files:** `custom_components/<domain>/coordinator/kalman.py` (new), `tests/coordinator/__init__.py`,
  `tests/coordinator/test_kalman.py` (new).
- **Changes:** `KalmanFusionFilter` — init from (N, σ_y, τ_bias, max_bias), `predict(dt)` with
  F/Q, `update(i, z, r)` with the N-th zero-sum row, interval-EMA `R` scaling hook, `resize(kept,
added)` with re-centring, `to_dict/from_dict`. Numpy.
- **Verification:** `script/test tests/coordinator` — convergence on constant signal, bias
  separation with two biased sensors, zero-sum invariant after resize/update, drift tracking under
  short τ, coasting through a simulated 6-hour gap, fast-sensor weight ≈ slow-sensor weight.
- **Independently shippable:** yes

### Phase 2 — Event-driven coordinator + persistence

- **Files:** rewrite `coordinator/base.py`, `coordinator/__init__.py`, `const.py`, `data.py`;
  `tests/coordinator/test_coordinator.py` (new), rewrite `tests/conftest.py`, delete
  `tests/test_coordinator.py`.
- **Changes:** coordinator subscribes on first-refresh, runs engine per event, publishes dataclass
  payload, Store load/save, `async_last_changed` availability handling (unavailable/unknown/non-
  numeric ignored), options → engine (re)build with resize. Delete `api/` usage.
- **Verification:** `script/test` green; engine state survives simulated reload in a test.
- **Independently shippable:** no (needs Phase 4 for a runnable UI)

### Phase 3 — Config & options flow

- **Files:** rewrite `config_flow_handler/{config_flow,options_flow}.py`,
  `schemas/{config,options}.py`, delete `validators/credentials.py` (+ `validators/` exports),
  rewrite `config_flow.py` shim if needed, `tests/test_config_flow.py`.
- **Changes:** user step = name + entity selector (multiple, ≥2, same device_class/unit enforced)
  - volatility/horizon/max-bias selectors with sane defaults and `data_description`; options flow
    same fields incl. add/remove sensors (`OptionsFlowWithReload`); drop reconfigure/reauth and
    credentials validators; errors `not_enough_sensors`, `mismatched_device_class`.
- **Verification:** `script/test tests/test_config_flow.py`, `script/hassfest`.
- **Independently shippable:** yes

### Phase 4 — Platforms (fusion sensor, bias sensors, reset button)

- **Files:** rewrite `sensor/{__init__,entity}.py`, new `sensor/fusion.py`, `sensor/bias.py`;
  adapt `entity/base.py`, `entity/__init__.py`; adapt `button/__init__.py` + rename
  `button/reset_filter.py` → `button/reset_fusion.py`; `__init__.py` (`PLATFORMS` = sensor +
  button, no client, setup order); **delete** `api/`, `binary_sensor/`, `fan/`, `number/`,
  `select/`, `switch/`, `service_actions/`, `services.yaml`, `schemas/yaml/*` if unused; delete
  matching `tests/` files; `diagnostics.py` redacted engine summary.
- **Changes:** fusion sensor inherits unit/device_class/state_class from inputs, `MEASUREMENT`,
  availability = any input available; one diagnostic bias sensor per input (name carries the
  source entity, value = learned bias, σ as attribute); reset button clears the Store + restarts
  engine. `ATTRIBUTION` removed.
- **Verification:** `script/test tests/test_entities.py` (rewrite), `script/hassfest`.
- **Independently shippable:** no

### Phase 5 — Strings, manifest, docs

- **Files:** `translations/en.json`, `icons.json`, `manifest.json` (helper/calculated/categories),
  `hacs.json` name, `README.md`, `docs/user/*`, `docs/development/DECISIONS.md` entries.
- **Changes:** every surviving entity/flow/error gets keys via `translation_key`; ADRs for
  event-driven vs polling, Store vs RestoreEntity, numpy use, no-unique-id/multi-instance.
- **Verification:** `script/hassfest`, `script/lint`, `script/markdown`.
- **Independently shippable:** yes

### Phase 6 — Full validation + live run

- **Files:** none new.
- **Changes:** `script/lint`, `script/type-check`, `script/hassfest`, `script/test` until green;
  `script/develop`, create entry against two synthetic sensors, watch fused + bias entities,
  restart HA, confirm biases persist; report exactly what ran.
- **Verification:** above.
- **Independently shippable:** n/a

## Breaking changes

None — no existing installations (fresh repository). Pre-1.0 shapes (options keys, Store format)
may still change without migration code; Store carries a version anyway.

## Risks and open questions

- **Identity values for `initialize.sh`** (domain/title/namespace/repo/author/category) — developer
  answers; blocks Phase 0 and everything after.
- **numpy at runtime** — HA core ships numpy so no requirement needed; fallback is a small
  dense-matrix module in the same file if the check tools object. Blocks nothing (Phase 1 decides).
- **Heart-rate bias sign with one active sensor** — with N-1 biases and only one sensor updating,
  the filter relies on the zero-sum prior; tests will pin the behaviour, but if it proves unstable
  the fallback is anchoring the last-seen sensor — Phase 1 decides, developer informed.
- **Entity-ID-based bias unique IDs** break when a source sensor is renamed; accepted for v1
  (pre-1.0, diagnostic entities only), noted in DECISIONS.md.
