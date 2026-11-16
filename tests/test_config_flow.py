"""Config and options flow tests for the sensor_fusion integration."""

from typing import TYPE_CHECKING

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensor_fusion.const import (
    CONF_BIAS_HORIZON,
    CONF_MAX_BIAS,
    CONF_SENSORS,
    CONF_VOLATILITY,
    DOMAIN,
)
from custom_components.sensor_fusion.sensor.bias import bias_entity_key
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_registry import EntityRegistry

pytestmark = pytest.mark.integration


def _user_input(**overrides: object) -> dict[str, object]:
    """Return a valid user-step submission with optional field overrides."""
    input_data: dict[str, object] = {
        CONF_NAME: "Living Room",
        CONF_SENSORS: ["sensor.ring_alpha", "sensor.ring_beta"],
        CONF_VOLATILITY: 2.0,
        CONF_BIAS_HORIZON: 480.0,
        CONF_MAX_BIAS: 10.0,
    }
    input_data.update(overrides)
    return input_data


async def test_user_flow_creates_entry(hass: HomeAssistant, set_source: Callable[..., None]) -> None:
    """The happy path shows the form once and creates a loaded entry."""
    set_source("sensor.ring_alpha", "70")
    set_source("sensor.ring_beta", "71")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=_user_input())
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room"
    assert result["data"][CONF_SENSORS] == ["sensor.ring_alpha", "sensor.ring_beta"]
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].state is ConfigEntryState.LOADED


async def test_user_flow_without_name_gets_default_title(hass: HomeAssistant, set_source: Callable[..., None]) -> None:
    """An empty name falls back to the integration title."""
    set_source("sensor.ring_alpha", "70")
    set_source("sensor.ring_beta", "71")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_user_input(**{CONF_NAME: ""})
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Sensor Fusion"


@pytest.mark.parametrize(
    "bad_sensors",
    [
        pytest.param(["sensor.ring_alpha"], id="one-source"),
        pytest.param(["sensor.ring_alpha", "sensor.ring_alpha"], id="duplicate-source"),
    ],
)
async def test_user_flow_requires_two_sensors(
    hass: HomeAssistant,
    set_source: Callable[..., None],
    bad_sensors: list[str],
) -> None:
    """Fewer than two distinct sensors re-shows the form with the matching error."""
    set_source("sensor.ring_alpha", "70")
    set_source("sensor.ring_beta", "71")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_user_input(**{CONF_SENSORS: bad_sensors})
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "not_enough_sensors"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=_user_input())
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_rejects_mismatched_units(hass: HomeAssistant, set_source: Callable[..., None]) -> None:
    """Sensors that disagree on unit cannot be fused; the error recovers once fixed."""
    set_source("sensor.ring_alpha", "70")
    set_source("sensor.ring_beta", "20", unit="°C")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=_user_input())
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "mismatched_sources"}

    set_source("sensor.ring_beta", "71")
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=_user_input())
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow_updates_settings_and_reloads(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    set_source: Callable[..., None],
    entity_registry: EntityRegistry,
) -> None:
    """Saving options stores them, reloads the entry and the new sensor gains a bias entity."""
    set_source("sensor.ring_gamma", "69")

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SENSORS: ["sensor.ring_alpha", "sensor.ring_beta", "sensor.ring_gamma"],
            CONF_VOLATILITY: 3.0,
            CONF_BIAS_HORIZON: 240.0,
            CONF_MAX_BIAS: 5.0,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert init_integration.options[CONF_SENSORS] == [
        "sensor.ring_alpha",
        "sensor.ring_beta",
        "sensor.ring_gamma",
    ]
    assert init_integration.state is ConfigEntryState.LOADED

    gamma_bias_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{init_integration.entry_id}_{bias_entity_key('sensor.ring_gamma')}"
    )
    assert gamma_bias_id is not None


async def test_options_flow_validates_like_setup(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
) -> None:
    """The options form refuses a one-sensor selection and recovers."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SENSORS: ["sensor.ring_alpha"],
            CONF_VOLATILITY: 2.0,
            CONF_BIAS_HORIZON: 480.0,
            CONF_MAX_BIAS: 10.0,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "not_enough_sensors"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SENSORS: ["sensor.ring_alpha", "sensor.ring_beta"],
            CONF_VOLATILITY: 2.0,
            CONF_BIAS_HORIZON: 480.0,
            CONF_MAX_BIAS: 10.0,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.LOADED
