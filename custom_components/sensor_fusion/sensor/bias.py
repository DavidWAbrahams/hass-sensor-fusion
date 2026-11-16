"""Per-source bias sensor for sensor_fusion."""

from collections.abc import Callable
import hashlib
from typing import TYPE_CHECKING

from custom_components.sensor_fusion.coordinator import SensorFusionCoordinator
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory

from .entity import SensorFusionSensor, SensorFusionSensorEntityDescription

if TYPE_CHECKING:
    from collections.abc import Mapping

    from custom_components.sensor_fusion.coordinator import SensorFusionFusionData, SensorFusionSourceStatus


def bias_entity_key(entity_id: str) -> str:
    """
    Return the stable description key for one source's bias entity.

    Derived from the source entity id rather than its slot so the entity keeps its identity when
    sensors are added, removed or reordered in the options.

    Args:
        entity_id: The source sensor's entity id.

    Returns:
        The `bias_...` key for the entity description.

    """
    return f"bias_{hashlib.sha1(entity_id.encode()).hexdigest()[:8]}"


class SensorFusionBiasSensor(SensorFusionSensor):
    """The bias the filter has learned for one input sensor."""

    def __init__(
        self,
        coordinator: SensorFusionCoordinator,
        description: SensorFusionSensorEntityDescription,
        slot: int,
    ) -> None:
        """Bind the entity to one source slot."""
        super().__init__(coordinator, description)
        self._slot = slot

    @property
    def _source(self) -> SensorFusionSourceStatus:
        """Return the current status of this entity's source sensor."""
        return self.coordinator.data.sources[self._slot]

    @property
    def translation_placeholders(self) -> Mapping[str, str]:
        """Return the source name the entity name is rendered with."""
        return {"source": self._source.name}

    @property
    def available(self) -> bool:
        """Return whether the source sensor currently reports a usable value."""
        return self._source.available

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit shared with the fused estimate."""
        return self.coordinator.data.unit

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class shared by the input sensors, when it is a known one."""
        raw = self.coordinator.data.device_class
        if raw is None:
            return None
        try:
            return SensorDeviceClass(raw)
        except ValueError:
            return None


def _bias_value(slot: int) -> Callable[[SensorFusionFusionData], float]:
    """Return the value_fn reading source ``slot``'s bias from the payload."""
    return lambda data: data.sources[slot].bias


def async_create_bias_entities(
    coordinator: SensorFusionCoordinator,
) -> list[SensorFusionBiasSensor]:
    """Build one bias sensor per configured source."""
    return [
        SensorFusionBiasSensor(
            coordinator,
            SensorFusionSensorEntityDescription(
                key=bias_entity_key(source.entity_id),
                translation_key="sensor_bias",
                entity_category=EntityCategory.DIAGNOSTIC,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=2,
                value_fn=_bias_value(source.slot),
            ),
            source.slot,
        )
        for source in coordinator.data.sources
    ]
