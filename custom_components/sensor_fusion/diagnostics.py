"""
Diagnostics support for sensor_fusion.

https://contributors.home-assistant.io/core/integrations/diagnostics/
"""

from typing import TYPE_CHECKING

from homeassistant.const import CONF_NAME
from homeassistant.helpers.redact import async_redact_data

if TYPE_CHECKING:
    from typing import Any

    from homeassistant.core import HomeAssistant

    from .data import SensorFusionConfigEntry

TO_REDACT = {CONF_NAME, "name", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: SensorFusionConfigEntry,
) -> dict[str, Any]:
    """
    Return diagnostics for a config entry.

    Returns:
        The redacted entry configuration and the filter's current state per source.

    """
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data

    return {
        "entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "state": str(entry.state),
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception) if coordinator.last_exception else None,
            "seeded": data.value is not None,
            "fused": data.value,
            "fused_stdev": data.stdev,
            "trend": data.trend,
            "unit": data.unit,
            "device_class": data.device_class,
            "sources": [
                {
                    "entity_id": source.entity_id,
                    "slot": source.slot,
                    "available": source.available,
                    "bias": source.bias,
                    "bias_stdev": source.bias_stdev,
                    "last_update": source.last_update,
                }
                for source in data.sources
            ],
        },
    }
