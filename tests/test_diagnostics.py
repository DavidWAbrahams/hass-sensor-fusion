"""Diagnostics tests for the sensor_fusion integration."""

from typing import TYPE_CHECKING

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensor_fusion.const import CONF_SENSORS
from custom_components.sensor_fusion.diagnostics import async_get_config_entry_diagnostics

if TYPE_CHECKING:
    from typing import Any

    from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.integration


async def test_diagnostics_redact_the_instance_name(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
) -> None:
    """The user-chosen instance name never reaches the diagnostics download."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    entry_data: dict[str, Any] = diagnostics["entry"]["data"]
    assert entry_data["name"] == "**REDACTED**"
    assert "Test Fusion" not in repr(diagnostics)


async def test_diagnostics_report_the_filter_state(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
) -> None:
    """The coordinator block carries the fused estimate and one source entry per sensor."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)

    coordinator: dict[str, Any] = diagnostics["coordinator"]
    assert coordinator["last_update_success"] is True
    assert coordinator["seeded"] is True
    assert coordinator["fused"] == pytest.approx(70.5)
    assert coordinator["unit"] == "bpm"
    assert coordinator["device_class"] is None

    sources = coordinator["sources"]
    assert [source["entity_id"] for source in sources] == list(init_integration.data[CONF_SENSORS])
    assert [source["slot"] for source in sources] == [0, 1]
    assert all(source["available"] for source in sources)
