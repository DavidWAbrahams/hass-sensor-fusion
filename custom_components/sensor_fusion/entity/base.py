"""Base entity class for sensor_fusion."""

from typing import TYPE_CHECKING

from custom_components.sensor_fusion.const import DOMAIN
from custom_components.sensor_fusion.coordinator import SensorFusionCoordinator
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity import EntityDescription


class SensorFusionEntity(CoordinatorEntity[SensorFusionCoordinator]):
    """
    Base entity providing device info and a stable unique ID.

    A fusion instance is a computed entity, not a device with a serial number, so the entry id is
    the identifier of record here rather than a fallback: the config entry is the thing the unique
    ID describes. The instance device is owned solely by this entry.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SensorFusionCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=coordinator.config_entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )
