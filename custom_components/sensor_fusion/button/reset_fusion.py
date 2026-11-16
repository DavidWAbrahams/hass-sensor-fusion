"""Reset fusion button for sensor_fusion."""

from custom_components.sensor_fusion.entity import SensorFusionEntity
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription

ENTITY_DESCRIPTIONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="reset_fusion",
        translation_key="reset_fusion",
    ),
)


class SensorFusionResetButton(ButtonEntity, SensorFusionEntity):
    """Button that discards the learned filter state and re-seeds from the current readings."""

    entity_description: ButtonEntityDescription

    async def async_press(self) -> None:
        """Reset the filter."""
        await self.coordinator.async_reset()
