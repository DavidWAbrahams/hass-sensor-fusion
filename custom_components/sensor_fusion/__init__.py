"""
Custom integration to integrate sensor_fusion with Home Assistant.

For more details about this integration, please refer to:
https://github.com/DavidWAbrahams/hass-sensor-fusion
"""

from typing import TYPE_CHECKING

from homeassistant.const import Platform
import homeassistant.helpers.config_validation as cv
from homeassistant.loader import async_get_loaded_integration

from .const import DOMAIN
from .coordinator import KalmanFusionFilter, SensorFusionCoordinator, SensorFusionSettings
from .data import SensorFusionData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import SensorFusionConfigEntry

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SensorFusionConfigEntry,
) -> bool:
    """
    Set up a config entry.

    Returns:
        True once the coordinator is listening and every platform is forwarded.

    """
    settings = SensorFusionSettings.from_entry(entry)
    if len(settings.sources) < 2:
        return False

    kalman_filter = KalmanFusionFilter(
        num_sensors=len(settings.sources),
        volatility=settings.volatility,
        bias_horizon_minutes=settings.bias_horizon_minutes,
        max_bias=settings.max_bias,
    )
    coordinator = SensorFusionCoordinator(hass, entry, settings, kalman_filter)
    await coordinator.async_start()

    entry.runtime_data = SensorFusionData(
        coordinator=coordinator,
        integration=async_get_loaded_integration(hass, entry.domain),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SensorFusionConfigEntry,
) -> bool:
    """
    Unload a config entry.

    Returns:
        True if every platform unloaded cleanly.

    """
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.coordinator.async_shutdown()
    return True
