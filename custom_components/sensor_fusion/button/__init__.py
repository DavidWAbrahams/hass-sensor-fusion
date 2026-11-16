"""Button platform for sensor_fusion."""

from typing import TYPE_CHECKING

from .reset_fusion import ENTITY_DESCRIPTIONS, SensorFusionResetButton

# The action itself is awaited on press, not polled.
PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from custom_components.sensor_fusion.data import SensorFusionConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SensorFusionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    async_add_entities(
        SensorFusionResetButton(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )
