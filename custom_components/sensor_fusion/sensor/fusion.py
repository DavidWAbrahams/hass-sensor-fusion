"""Fused value sensor for sensor_fusion."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from .entity import SensorFusionSensor, SensorFusionSensorEntityDescription

ENTITY_DESCRIPTIONS: tuple[SensorFusionSensorEntityDescription, ...] = (
    SensorFusionSensorEntityDescription(
        key="fusion",
        translation_key="fused_value",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.value,
    ),
)


class SensorFusionFusionSensor(SensorFusionSensor):
    """The fused estimate, reported in the unit and class the input sensors share."""

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit taken from the input sensors."""
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
