"""Shared fixtures for the sensor_fusion tests."""

from collections.abc import Callable, Generator
from functools import partial
import logging
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
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_FRIENDLY_NAME, ATTR_UNIT_OF_MEASUREMENT, CONF_NAME

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State
    from homeassistant.helpers.entity_registry import EntityRegistry

# Two heart-rate rings and a third held in reserve for add/remove scenarios.
SOURCE_ONE = "sensor.ring_alpha"
SOURCE_TWO = "sensor.ring_beta"
SOURCE_THREE = "sensor.ring_gamma"

DEFAULT_VALUES: dict[str, str] = {SOURCE_ONE: "70", SOURCE_TWO: "71"}

SOURCE_NAMES: dict[str, str] = {
    SOURCE_ONE: "Ring Alpha",
    SOURCE_TWO: "Ring Beta",
    SOURCE_THREE: "Ring Gamma",
}


def _set_source(
    hass: HomeAssistant,
    entity_id: str,
    value: str = "70",
    *,
    unit: str = "bpm",
    device_class: str | None = None,
    friendly_name: str | None = None,
) -> None:
    """Put one source sensor into hass with the attributes the integration reads."""
    attributes: dict[str, str] = {}
    if unit:
        attributes[ATTR_UNIT_OF_MEASUREMENT] = unit
    if device_class is not None:
        attributes[ATTR_DEVICE_CLASS] = device_class
    name = friendly_name if friendly_name is not None else SOURCE_NAMES.get(entity_id)
    if name:
        attributes[ATTR_FRIENDLY_NAME] = name
    hass.states.async_set(entity_id, value, attributes)


def _state_for_unique_id(
    hass: HomeAssistant,
    entity_registry: EntityRegistry,
    platform: str,
    unique_id: str,
) -> State:
    """
    Return the state of the entity registered under a unique id.

    Raises:
        AssertionError: If no entity is registered under that unique id.

    """
    entity_id = entity_registry.async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, f"no {platform} entity registered with unique id {unique_id}"
    state = hass.states.get(entity_id)
    assert state is not None, f"entity {entity_id} has no state"
    return state


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom integrations in every test."""


@pytest.fixture(autouse=True)
def fail_on_deprecation_report(caplog: pytest.LogCaptureFixture) -> Generator[None]:
    """Fail a test when Home Assistant logs a deprecation this integration caused."""
    yield
    reports = [
        message
        for record in [*caplog.get_records("setup"), *caplog.get_records("call")]
        if record.levelno >= logging.WARNING
        and DOMAIN in (message := record.getMessage())
        and message.startswith(("Detected that custom integration", "The deprecated"))
    ]
    assert not reports, "\n".join(reports)


@pytest.fixture
def config_entry(request: pytest.FixtureRequest) -> MockConfigEntry:
    """
    Return a config entry for this integration.

    Parametrize indirectly with a dict of extra or overriding entry data.
    """
    overrides: dict[str, object] = getattr(request, "param", {})
    data: dict[str, object] = {
        CONF_NAME: "Test Fusion",
        CONF_SENSORS: [SOURCE_ONE, SOURCE_TWO],
        CONF_VOLATILITY: 2.0,
        CONF_BIAS_HORIZON: 480.0,
        CONF_MAX_BIAS: 10.0,
        **overrides,
    }
    return MockConfigEntry(domain=DOMAIN, title="Test Fusion", data=data)


@pytest.fixture
def set_source(hass: HomeAssistant) -> Callable[..., None]:
    """Return the source-state helper bound to this test's hass."""
    return partial(_set_source, hass)


@pytest.fixture
def state_for_unique_id(
    hass: HomeAssistant,
    entity_registry: EntityRegistry,
) -> Callable[[str, str], State]:
    """Return the state lookup helper bound to this test's hass and entity registry."""
    return partial(_state_for_unique_id, hass, entity_registry)


@pytest.fixture
async def init_integration(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    """
    Place the source sensors, set up the config entry and return it loaded.

    Returns:
        The config entry, now loaded.

    """
    for entity_id, value in DEFAULT_VALUES.items():
        _set_source(hass, entity_id, value)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
