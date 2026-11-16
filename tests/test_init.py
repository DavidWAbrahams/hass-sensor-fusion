"""Setup, entity and lifecycle tests for the sensor_fusion integration."""

from typing import TYPE_CHECKING

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensor_fusion.const import CONF_SENSORS, DOMAIN
from custom_components.sensor_fusion.sensor.bias import bias_entity_key
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant, State
    from homeassistant.helpers.entity_registry import EntityRegistry

pytestmark = pytest.mark.integration

FUSED_KEY = "fusion"


def _bias_key(source: str) -> str:
    """Return the fused-unique-id suffix for one source's bias entity."""
    return bias_entity_key(source)


async def test_setup_loads_entry_and_seeds_the_fused_estimate(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    state_for_unique_id: Callable[[str, str], State],
) -> None:
    """A fresh instance seeds from the current readings and exposes them as entities."""
    assert init_integration.state is ConfigEntryState.LOADED

    fused = state_for_unique_id("sensor", f"{init_integration.entry_id}_{FUSED_KEY}")
    assert fused.state == "70.5"
    assert fused.attributes[ATTR_UNIT_OF_MEASUREMENT] == "bpm"
    assert fused.attributes["state_class"] == "measurement"
    assert "device_class" not in fused.attributes

    bias_one = state_for_unique_id("sensor", f"{init_integration.entry_id}_{_bias_key('sensor.ring_alpha')}")
    bias_two = state_for_unique_id("sensor", f"{init_integration.entry_id}_{_bias_key('sensor.ring_beta')}")
    assert bias_one.state == "-0.5"
    assert bias_two.state == "0.5"


async def test_entities_share_one_service_device(
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The instance appears as a single service device owned by its config entry."""
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, init_integration.entry_id),
        init_integration.entry_id,
    )
    assert device is not None
    assert device.name == "Test Fusion"
    assert device.entry_type is DeviceEntryType.SERVICE


async def test_bias_entities_are_diagnostic(
    init_integration: MockConfigEntry,
    entity_registry: EntityRegistry,
) -> None:
    """The per-source bias entities are diagnostic, the fused estimate is a user entity."""
    fused_id = entity_registry.async_get_entity_id("sensor", DOMAIN, f"{init_integration.entry_id}_{FUSED_KEY}")
    bias_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{init_integration.entry_id}_{_bias_key('sensor.ring_alpha')}"
    )
    assert fused_id is not None
    assert bias_id is not None
    fused_entry = entity_registry.async_get(fused_id)
    bias_entry = entity_registry.async_get(bias_id)
    assert fused_entry is not None and fused_entry.entity_category is None
    assert bias_entry is not None and bias_entry.entity_category is EntityCategory.DIAGNOSTIC


async def test_source_update_moves_the_fused_estimate(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    set_source: Callable[..., None],
    state_for_unique_id: Callable[[str, str], State],
) -> None:
    """A new reading advances the estimate toward it instead of snapping to it."""
    set_source("sensor.ring_alpha", "75")
    await hass.async_block_till_done()

    fused = float(state_for_unique_id("sensor", f"{init_integration.entry_id}_{FUSED_KEY}").state)
    assert 71.0 < fused < 74.99


@pytest.mark.parametrize("broken_state", [STATE_UNAVAILABLE, STATE_UNKNOWN, "unstable"])
async def test_unusable_source_state_is_ignored(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    set_source: Callable[..., None],
    state_for_unique_id: Callable[[str, str], State],
    broken_state: str,
) -> None:
    """Unavailable, unknown and non-numeric readings leave the estimate coasting."""
    set_source("sensor.ring_alpha", broken_state)
    await hass.async_block_till_done()

    assert state_for_unique_id("sensor", f"{init_integration.entry_id}_{FUSED_KEY}").state == "70.5"


async def test_unavailable_source_marks_only_its_bias_entity(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    set_source: Callable[..., None],
    state_for_unique_id: Callable[[str, str], State],
) -> None:
    """Availability is per source: an outage greys out that source's bias entity only."""
    set_source("sensor.ring_alpha", STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    bias_key = f"{init_integration.entry_id}_{_bias_key('sensor.ring_alpha')}"
    assert state_for_unique_id("sensor", bias_key).state == STATE_UNAVAILABLE
    assert state_for_unique_id("sensor", f"{init_integration.entry_id}_{FUSED_KEY}").state == "70.5"

    set_source("sensor.ring_alpha", "70")
    await hass.async_block_till_done()
    assert state_for_unique_id("sensor", bias_key).state != STATE_UNAVAILABLE


async def test_learned_state_survives_a_reload(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    set_source: Callable[..., None],
    state_for_unique_id: Callable[[str, str], State],
) -> None:
    """A reload restores the learned filter instead of re-seeding from the raw readings."""
    for _ in range(3):
        set_source("sensor.ring_alpha", "75")
        await hass.async_block_till_done()

    bias_key = f"{init_integration.entry_id}_{_bias_key('sensor.ring_alpha')}"
    pre_reload_bias = state_for_unique_id("sensor", bias_key).state
    pre_reload_fused = state_for_unique_id("sensor", f"{init_integration.entry_id}_{FUSED_KEY}").state
    # The observation model is obs_i = y + b_i, so the sensor reading high gains a positive bias.
    assert float(pre_reload_bias) > 0.5
    assert 71.0 < float(pre_reload_fused) < 74.99

    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert state_for_unique_id("sensor", bias_key).state == pre_reload_bias
    assert state_for_unique_id("sensor", f"{init_integration.entry_id}_{FUSED_KEY}").state == pre_reload_fused


async def test_reset_button_re_seeds_from_current_readings(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    set_source: Callable[..., None],
    entity_registry: EntityRegistry,
    state_for_unique_id: Callable[[str, str], State],
) -> None:
    """Pressing the reset button discards the learned state and re-seeds."""
    for _ in range(2):
        set_source("sensor.ring_alpha", "75")
        await hass.async_block_till_done()
    assert float(state_for_unique_id("sensor", f"{init_integration.entry_id}_{FUSED_KEY}").state) > 71.0

    button_id = entity_registry.async_get_entity_id("button", DOMAIN, f"{init_integration.entry_id}_reset_fusion")
    assert button_id is not None
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: button_id}, blocking=True)
    await hass.async_block_till_done()

    assert state_for_unique_id("sensor", f"{init_integration.entry_id}_{FUSED_KEY}").state == "73.0"
    assert state_for_unique_id("sensor", f"{init_integration.entry_id}_{_bias_key('sensor.ring_alpha')}").state == "2.0"


async def test_two_instances_run_side_by_side(
    init_integration: MockConfigEntry,
    hass: HomeAssistant,
    set_source: Callable[..., None],
    entity_registry: EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Two config entries fuse independently and own separate devices."""
    set_source("sensor.ring_gamma", "68")
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Second Fusion",
        data={CONF_SENSORS: ["sensor.ring_alpha", "sensor.ring_gamma"]},
    )
    second_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(second_entry.entry_id)
    await hass.async_block_till_done()

    assert second_entry.state is ConfigEntryState.LOADED

    first_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, init_integration.entry_id), init_integration.entry_id
    )
    second_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, second_entry.entry_id), second_entry.entry_id
    )
    assert first_device is not None and first_device.name == "Test Fusion"
    assert second_device is not None and second_device.name == "Second Fusion"

    second_fused_id = entity_registry.async_get_entity_id("sensor", DOMAIN, f"{second_entry.entry_id}_{FUSED_KEY}")
    assert second_fused_id is not None
    second_fused = hass.states.get(second_fused_id)
    assert second_fused is not None
    assert second_fused.state == "69.0"


@pytest.mark.parametrize(
    "config_entry",
    [
        pytest.param({CONF_SENSORS: ["sensor.ring_alpha"]}, id="single-source"),
        pytest.param({CONF_SENSORS: []}, id="no-sources"),
    ],
    indirect=True,
)
async def test_entry_with_fewer_than_two_sources_fails_setup(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Fusion needs at least two sensors; the entry refuses to load without them."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
