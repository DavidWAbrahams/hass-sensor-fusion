"""Event-driven coordinator for sensor_fusion."""

from dataclasses import dataclass
import math
import time
from typing import TYPE_CHECKING, Self

from custom_components.sensor_fusion.const import (
    CONF_BIAS_HORIZON,
    CONF_MAX_BIAS,
    CONF_SENSORS,
    CONF_VOLATILITY,
    DEFAULT_BIAS_HORIZON,
    DEFAULT_MAX_BIAS,
    DEFAULT_VOLATILITY,
    DOMAIN,
    LOGGER,
)
from custom_components.sensor_fusion.coordinator.kalman import KalmanFusionFilter
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

if TYPE_CHECKING:
    from collections.abc import Callable

    from custom_components.sensor_fusion.data import SensorFusionConfigEntry
    from homeassistant.core import HomeAssistant

STORAGE_VERSION = 1
SAVE_THROTTLE_SECONDS = 300.0


@dataclass(frozen=True)
class SensorFusionSettings:
    """The merged config entry settings describing one fusion instance."""

    sources: tuple[str, ...]
    volatility: float
    bias_horizon_minutes: float
    max_bias: float

    @classmethod
    def from_entry(cls, entry: SensorFusionConfigEntry) -> Self:
        """
        Merge the entry's setup data with its options, options winning.

        Returns:
            The settings every layer reads.

        """
        merged = {**entry.data, **entry.options}
        return cls(
            sources=tuple(merged[CONF_SENSORS]),
            volatility=float(merged.get(CONF_VOLATILITY, DEFAULT_VOLATILITY)),
            bias_horizon_minutes=float(merged.get(CONF_BIAS_HORIZON, DEFAULT_BIAS_HORIZON)),
            max_bias=float(merged.get(CONF_MAX_BIAS, DEFAULT_MAX_BIAS)),
        )


@dataclass(frozen=True, slots=True)
class SensorFusionSourceStatus:
    """What the filter currently knows about one input sensor."""

    entity_id: str
    slot: int
    name: str
    available: bool
    bias: float
    bias_stdev: float
    last_update: float | None


@dataclass(frozen=True, slots=True)
class SensorFusionFusionData:
    """The payload every entity reads from the coordinator."""

    value: float | None
    stdev: float | None
    trend: float | None
    last_update: float | None
    unit: str | None
    device_class: str | None
    sources: tuple[SensorFusionSourceStatus, ...]


class SensorFusionCoordinator(DataUpdateCoordinator[SensorFusionFusionData]):
    """
    Drive the Kalman filter from state change events instead of polling.

    The filter is advanced on every valid numeric reading of a source sensor; the fused estimate and
    the per-sensor biases are published to the entities through the coordinator payload. The filter
    state is persisted so learned biases survive restarts and reloads.
    """

    config_entry: SensorFusionConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: SensorFusionConfigEntry,
        settings: SensorFusionSettings,
        kalman_filter: KalmanFusionFilter,
    ) -> None:
        """Set up the coordinator for one config entry; call async_start to activate it."""
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=config_entry, update_interval=None)
        self._settings = settings
        self._filter = kalman_filter
        self._sources = list(settings.sources)
        self._slot = {entity_id: slot for slot, entity_id in enumerate(self._sources)}
        self._unsub: Callable[[], None] | None = None
        self._store: Store[dict[str, object]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}_state.{config_entry.entry_id}")
        self._dirty = False
        self._last_save = 0.0

    async def async_start(self) -> None:
        """Restore the saved filter, seed it from the current states and subscribe to the sources."""
        await self._async_restore()
        if not self._filter.seeded:
            self._async_seed_from_states()
        self.async_set_updated_data(self._build_payload())
        self._unsub = async_track_state_change_event(self.hass, self._sources, self._async_state_changed)

    async def async_shutdown(self) -> None:
        """Stop listening and flush the filter state to storage."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._dirty:
            await self._store.async_save(self._saved_payload())
        await super().async_shutdown()

    async def async_reset(self) -> None:
        """Discard the learned state, re-seed from the current readings and publish the fresh filter."""
        self._filter = KalmanFusionFilter(
            num_sensors=len(self._sources),
            volatility=self._settings.volatility,
            bias_horizon_minutes=self._settings.bias_horizon_minutes,
            max_bias=self._settings.max_bias,
        )
        self._async_seed_from_states()
        self._dirty = True
        self._schedule_save()
        self.async_set_updated_data(self._build_payload())

    async def _async_update_data(self) -> SensorFusionFusionData:
        """
        Rebuild the payload; the filter itself only moves on state change events.

        Returns:
            The current fusion payload.

        """
        return self._build_payload()

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Advance the filter with one source update and publish the result."""
        slot = self._slot[event.data["entity_id"]]
        value = self._async_valid_value(event.data["entity_id"])
        if value is not None:
            timestamp = event.time_fired.timestamp() if event.time_fired else time.time()
            self._filter.step(slot, value, timestamp)
            self._dirty = True
            now = time.monotonic()
            if now - self._last_save >= SAVE_THROTTLE_SECONDS:
                self._last_save = now
                self._schedule_save()
        self.async_set_updated_data(self._build_payload())

    async def _async_restore(self) -> None:
        """Reload the persisted filter, reshaping it to the current sensor list and options."""
        saved = await self._store.async_load()
        if isinstance(saved, dict):
            filter_data = saved.get("filter")
            raw_sources = saved.get("sources", [])
            if isinstance(filter_data, dict) and isinstance(raw_sources, list):
                saved_sources = [str(entity_id) for entity_id in raw_sources]
                try:
                    restored = KalmanFusionFilter.from_dict(filter_data)
                except ValueError, KeyError, TypeError:
                    self.logger.warning("Discarding unreadable saved filter state; starting fresh")
                else:
                    self._filter = self._async_reshaped(restored, saved_sources)
        self._filter.update_config(
            volatility=self._settings.volatility,
            bias_horizon_minutes=self._settings.bias_horizon_minutes,
            max_bias=self._settings.max_bias,
        )

    def _async_reshaped(self, restored: KalmanFusionFilter, saved_sources: list[str]) -> KalmanFusionFilter:
        """
        Return the restored filter resized to the current sources, or the fresh filter if unusable.

        Args:
            restored: The filter as saved, keyed by the saved source order.
            saved_sources: The entity ids the saved filter's slots referred to.

        Returns:
            The filter the coordinator should run.

        """
        if restored.num_sensors != len(saved_sources):
            self.logger.warning("Saved filter state does not match its saved sources; starting fresh")
            return self._filter
        old_slot = {entity_id: slot for slot, entity_id in enumerate(saved_sources)}
        keep = [old_slot.get(entity_id) for entity_id in self._sources]
        if len([old for old in keep if old is not None]) < 2:
            return self._filter
        if keep != list(range(restored.num_sensors)):
            restored.resize(keep)
        return restored

    def _async_seed_from_states(self) -> None:
        """Seed the filter from every source that already holds a valid reading."""
        measurements: dict[int, float] = {}
        for slot, entity_id in enumerate(self._sources):
            value = self._async_valid_value(entity_id)
            if value is not None:
                measurements[slot] = value
        self._filter.seed(measurements)

    def _async_valid_value(self, entity_id: str) -> float | None:
        """Return the entity's current numeric state, or None if it holds no usable measurement."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    def _async_source_name(self, entity_id: str) -> str:
        """Return the friendly name of a source, falling back to its entity id."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return entity_id
        name = state.attributes.get(ATTR_FRIENDLY_NAME)
        return name if isinstance(name, str) and name else entity_id

    def _build_payload(self) -> SensorFusionFusionData:
        """Snapshot the filter and the source availability into the entity-facing payload."""
        biases = self._filter.biases()
        sources = tuple(
            SensorFusionSourceStatus(
                entity_id=entity_id,
                slot=slot,
                name=self._async_source_name(entity_id),
                available=self._async_valid_value(entity_id) is not None,
                bias=biases[slot],
                bias_stdev=math.sqrt(self._filter.bias_variance(slot)),
                last_update=self._filter.stats[slot].last_update,
            )
            for slot, entity_id in enumerate(self._sources)
        )
        variance = self._filter.fused_variance
        unit: str | None = None
        device_class: str | None = None
        for entity_id in self._sources:
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            device_class = state.attributes.get(ATTR_DEVICE_CLASS)
            if unit or device_class:
                break
        return SensorFusionFusionData(
            value=self._filter.fused,
            stdev=math.sqrt(variance) if self._filter.seeded else None,
            trend=self._filter.trend,
            last_update=self._filter.last_update,
            unit=unit,
            device_class=device_class,
            sources=sources,
        )

    def _saved_payload(self) -> dict[str, object]:
        """Return the storage document: the filter state and the entity ids its slots refer to."""
        return {"sources": list(self._sources), "filter": self._filter.to_dict()}

    def _schedule_save(self) -> None:
        """Persist the filter state without making the event path wait for disk."""
        self.config_entry.async_create_background_task(
            self.hass, self._store.async_save(self._saved_payload()), "sensor_fusion state save"
        )


__all__ = [
    "SensorFusionCoordinator",
    "SensorFusionFusionData",
    "SensorFusionSettings",
    "SensorFusionSourceStatus",
]
