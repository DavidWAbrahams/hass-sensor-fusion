"""Sensor platform for sensor_fusion."""

from typing import TYPE_CHECKING

from .bias import async_create_bias_entities
from .fusion import ENTITY_DESCRIPTIONS as FUSION_DESCRIPTIONS, SensorFusionFusionSensor

# Read-only platform: the filter only moves on state change events.
PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.sensor_fusion.data import SensorFusionConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SensorFusionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform: the fused value plus one bias entity per source."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [SensorFusionFusionSensor(coordinator, description) for description in FUSION_DESCRIPTIONS]
        + async_create_bias_entities(coordinator)
    )
