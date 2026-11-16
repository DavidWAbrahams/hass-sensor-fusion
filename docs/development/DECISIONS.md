# Architectural and Design Decisions

This document records significant architectural and design decisions made during the development of this integration.

## Format

Each decision is documented with:

- **Date:** When the decision was made
- **Context:** Why this decision was necessary
- **Decision:** What was decided
- **Rationale:** Why this approach was chosen
- **Consequences:** Expected impacts and trade-offs

> [!NOTE]
> Guidance on _when_ a decision is worth recording here, and a copy-ready entry template, lives in the
> [`ha-planning`](../../.agents/skills/ha-planning/SKILL.md) agent skill.

---

## Decision Log

### Use DataUpdateCoordinator for All Data Fetching

**Date:** 2025-11-29 (Template initialization)

**Context:** The integration needs to fetch data from an external API and share it with multiple entities. Home Assistant provides several patterns for this.

**Decision:** Use `DataUpdateCoordinator` from `homeassistant.helpers.update_coordinator` as the central data management component.

**Rationale:**

- Provides built-in support for update intervals and error handling
- Automatic retry with exponential backoff
- Shared data access prevents duplicate API calls
- Standard pattern recommended by Home Assistant
- Entities automatically become unavailable when coordinator fails

**Consequences:**

- All entities must inherit from `CoordinatorEntity`
- Single update interval applies to all entities
- Data is fetched even if no entities are enabled
- Coordinator manages entity lifecycle and availability

---

### Separate API Client from Coordinator

**Date:** 2025-11-29 (Template initialization)

**Context:** The coordinator needs to fetch data, but business logic should be separated from data transport.

**Decision:** Implement API communication in separate `api/client.py` module, coordinator only orchestrates updates.

**Rationale:**

- Separation of concerns: transport vs. orchestration
- Easier to test API client in isolation
- Simpler to swap API implementation if needed
- Clearer error handling boundaries

**Consequences:**

- Additional abstraction layer
- Coordinator depends on API client
- API client raises custom exceptions for error translation

---

### Platform-Specific Directories

**Date:** 2025-11-29 (Template initialization)

**Context:** Integration supports multiple platforms (sensor, binary_sensor, switch, etc.).

**Decision:** Each platform gets its own directory with individual entity files.

**Rationale:**

- Clear organization as integration grows
- Easier to find specific entity implementations
- Supports multiple entities per platform cleanly
- Follows Home Assistant Core pattern

**Consequences:**

- More files/directories than single-file approach
- Platform `__init__.py` must import and register entities
- Slightly more initial setup overhead

---

### EntityDescription for Static Metadata

**Date:** 2025-11-29 (Template initialization)

**Context:** Entities have static metadata (name, icon, device class) that doesn't change.

**Decision:** Use `EntityDescription` dataclasses to define static entity metadata.

**Rationale:**

- Declarative and easy to read
- Type-safe with dataclasses
- Recommended Home Assistant pattern
- Separates static configuration from dynamic behavior

**Consequences:**

- Each entity type needs an EntityDescription
- Dynamic entities need custom handling
- Static and dynamic properties clearly separated

---

### Event-Driven Updates Instead of Polling

**Date:** 2026-11-15 (Sensor Fusion implementation)

**Context:** The inputs are Home Assistant sensor entities, so new measurements arrive as state-change events at irregular intervals (minutes to hours apart for wearable sensors). Polling on a fixed interval would either add latency past the point of usefulness or wake the filter constantly to find nothing new.

**Decision:** The coordinator subscribes with `async_track_state_change_event` and runs one predict-then-update Kalman cycle per accepted event. There is no periodic update; through an outage the filter coasts via the trend state.

**Rationale:**

- The integration fetches from no external source — Home Assistant's own state machine is the stream, and events are its push mechanism
- A poll interval fast enough for real-time responsiveness would be wasteful for sources that report every 30 minutes
- The elapsed-time projection in the filter makes irregular arrivals exact, not approximated

**Consequences:**

- `DataUpdateCoordinator` is used without a polling interval (`_async_update_data` only publishes existing state), which deviates from the blueprint's fetch-oriented coordinator
- Coordinator failures cannot surface as update retries; there is nothing to retry — invalid events are simply ignored
- Test suites must drive state changes rather than mock a client

---

### Constrained Zero-Sum Bias Estimation

**Date:** 2026-11-15 (Sensor Fusion implementation)

**Context:** Fusing N biased sensors needs a bias per sensor, but adding N biases makes the state unidentifiable: a common offset shared by all sensors is indistinguishable from the fused value.

**Decision:** Track only N − 1 biases in the state `x = [y, ẏ, b₁ … b_{N−1}]`, constrain them to sum to zero, and treat the N-th sensor's bias as the implicit `−Σbᵢ`. Sensor i reports `y + bᵢ`, so its observation row is `[1, 0, …, +1 at bᵢ, …]` and the last sensor's is `[1, 0, −1, …, −1]`.

**Rationale:**

- Removes the rank deficiency that makes the unconstrained covariance singular
- The remaining freedom (a common offset absorbed into y) is harmless for a fused estimate
- Keeps the state small and the update a single row-vector operation

**Consequences:**

- Individual bias entities read relative to the group mean, not absolute; a bias common to every input appears in the fused value, not the biases
- Options-flow resize must re-centre biases to preserve the constraint
- Documented in the module docstring of `coordinator/kalman.py` and asserted in its tests

---

### Filter State Persisted with helpers.storage.Store

**Date:** 2026-11-15 (Sensor Fusion implementation)

**Context:** The learned biases are worth minutes-to-days of observations. Losing them on every restart or options change would make the integration feel amnesiac.

**Decision:** The coordinator serialises the filter state (`to_dict`) through one `homeassistant.helpers.storage.Store` per config entry (`sensor_fusion_{entry_id}`, version 1), saved throttled (300 s, first save immediate) and flushed on shutdown; it is restored on setup and resized to the new sensor list on reload.

**Rationale:**

- `RestoreEntity` restores only one entity's state string, not a covariance matrix or per-sensor timing history, and only for the entity that registered it
- `Store` is the supported way to persist integration-owned state, is loaded before entities are created, and survives upgrades
- One document per entry keeps multi-instance setups isolated

**Consequences:**

- Entities stay stateless; only the coordinator owns persistence
- A corrupt saved document is caught on load and the filter falls back to seeding from current readings
- The saved payload carries entity IDs, so the options flow maps old slots to new ones when the sensor list changes

---

### numpy as a Runtime Dependency

**Date:** 2026-11-15 (Sensor Fusion implementation)

**Context:** Each update touches a dense (2 + N − 1)² covariance. The matrix products could be hand-rolled in Python lists.

**Decision:** Depend on `numpy` (pinned in both `manifest.json` and `requirements.txt`) for the small dense linear algebra in `coordinator/kalman.py`.

**Rationale:**

- No maintained PyPI library does this constrained fusion, so an own client was the alternative considered; the question here was only the math backend
- numpy is already a transitive dependency of Home Assistant (`homeassistant/util/json.py` and friends) — the effective footprint is near zero
- A hand-rolled implementation would need its own numerical validation for exactly the operations numpy is battle-tested on

**Consequences:**

- `numpy` appears in the manifest requirements and must be kept in sync with `requirements.txt`
- All state objects are numpy arrays; JSON persistence converts via `.tolist()`
- No import outside `coordinator/kalman.py`, keeping the rest of the integration numpy-free

---

### Unique IDs Scoped to the Config Entry

**Date:** 2026-11-15 (Sensor Fusion implementation)

**Context:** A fusion instance has no serial number, MAC or account ID — it is a user-defined grouping of existing entities. The blueprint's config flow guidance forbids entity IDs or names as unique IDs.

**Decision:** The config entry is created without a unique ID, and every entity's unique ID is `{config_entry_id}_{key}` (bias entities additionally carry the SHA-1 prefix of the source entity ID).

**Rationale:**

- There is no stable device or account identifier to use; the config entry ID is the only stable handle, and the config-flow rules list "no unique ID" as valid for user-defined groupings, which also permits multiple independent instances
- Deriving an ID from the selected sensor list would change whenever the options flow edits it, orphaning the entity registry

**Consequences:**

- The entry cannot be deduplicated on rediscovery or reconfigured by unique ID lookup (none is needed — YAML is not supported)
- Reloading and options changes keep entity IDs stable because the entry ID is stable
- Bias entities churn (old removed, new created) exactly when their source leaves or joins, which matches expectations

---

### Options Flow with Reload Instead of a Reconfigure Flow

**Date:** 2026-11-15 (Sensor Fusion implementation)

**Context:** Changing the sensor set must resize the filter and changing tuning parameters must reach the live filter.

**Decision:** All changes go through the options flow (`OptionsFlowWithReload`), writing to `entry.options`; the merged view `{**entry.data, **entry.options}` is the single settings source. No reconfigure step.

**Rationale:**

- Options keep `entry.data` (the setup snapshot) immutable, so re-authentication and migration surface stays simple
- `OptionsFlowWithReload` gives the resize-on-reload behaviour for free; the coordinator hot-swaps tuning via `update_config` when the filter itself survives the change
- A reconfigure flow would duplicate the form for no gain since nothing needs re-validating credentials against

**Consequences:**

- Settings are read through `SensorFusionSettings.from_entry`, never `entry.data[key]` directly
- A sensor-set change reloads the entry, briefly unloading entities; the filter state survives through the `Store`
- Validation errors in options mirror setup's (`not_enough_sensors`, `mismatched_sources`)

---

## Future Considerations

### Multi-Device Support

**Status:** Not yet implemented

Current architecture assumes single device per config entry. If multi-device support is needed, coordinator data structure will need redesign to map device ID → data.

### Discovery

**Status:** Not yet implemented

Fusion instances are user-defined groupings with nothing to discover. If a hub-like discovery source is ever added, subentries could model groups of sensors under one parent entry.

---

## Decision Review

These decisions should be reviewed periodically (suggested: quarterly or when major features are added) to ensure they still serve the integration's needs.
