"""Sensor entity for sensor_fusion."""

from collections.abc import Callable
from dataclasses import dataclass

from custom_components.sensor_fusion.coordinator import SensorFusionFusionData
from custom_components.sensor_fusion.entity import SensorFusionEntity
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.typing import StateType


@dataclass(frozen=True, kw_only=True)
class SensorFusionSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor and how to read it from the fusion payload."""

    value_fn: Callable[[SensorFusionFusionData], StateType]


class SensorFusionSensor(SensorEntity, SensorFusionEntity):
    """Sensor backed by one value in the coordinator payload."""

    entity_description: SensorFusionSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the value read from the coordinator payload."""
        return self.entity_description.value_fn(self.coordinator.data)
