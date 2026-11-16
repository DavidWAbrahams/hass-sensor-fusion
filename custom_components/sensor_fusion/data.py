"""
Runtime data types for sensor_fusion.

Access pattern: entry.runtime_data.coordinator
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .coordinator import SensorFusionCoordinator


type SensorFusionConfigEntry = ConfigEntry[SensorFusionData]


@dataclass
class SensorFusionData:
    """Runtime data stored on the config entry after a successful setup."""

    coordinator: SensorFusionCoordinator
    integration: Integration
