"""Tests for restoring the persisted filter state on setup.

The saved filter lives in Home Assistant storage under ``sensor_fusion_state.<entry_id>``; the
``hass_storage`` fixture lets a test place a document there before the entry is set up, so the
restore path is exercised end to end through ``hass.states``.
"""

from typing import TYPE_CHECKING

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensor_fusion.const import DOMAIN
from custom_components.sensor_fusion.coordinator.kalman import KalmanFusionFilter
from custom_components.sensor_fusion.sensor.bias import bias_entity_key
from homeassistant.config_entries import ConfigEntryState

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant, State

pytestmark = pytest.mark.integration

FUSED_KEY = "fusion"
SOURCE_ALPHA = "sensor.ring_alpha"
SOURCE_BETA = "sensor.ring_beta"


def _store_key(entry_id: str) -> str:
    """Return the storage key the coordinator persists this entry's filter under."""
    return f"{DOMAIN}_state.{entry_id}"


def _saved_filter_state(first: float, second: float) -> dict[str, object]:
    """Return a saved filter document seeded with ``first`` in slot 0 and ``second`` in slot 1."""
    filter_obj = KalmanFusionFilter(num_sensors=2, volatility=2.0, bias_horizon_minutes=480.0, max_bias=10.0)
    filter_obj.seed({0: first, 1: second})
    return filter_obj.to_dict()


async def test_corrupt_saved_filter_state_falls_back_to_fresh_seed(
    hass: HomeAssistant,
    hass_storage: dict[str, object],
    config_entry: MockConfigEntry,
    set_source: Callable[..., None],
    state_for_unique_id: Callable[[str, str], State],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unreadable saved filter is discarded with a warning and the entry still loads."""
    set_source(SOURCE_ALPHA, "70")
    set_source(SOURCE_BETA, "71")
    config_entry.add_to_hass(hass)
    corrupt_filter = _saved_filter_state(77.0, 73.0) | {"version": 999}
    hass_storage[_store_key(config_entry.entry_id)] = {
        "version": 1,
        "data": {"sources": [SOURCE_ALPHA, SOURCE_BETA], "filter": corrupt_filter},
    }

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert "Discarding unreadable saved filter state" in caplog.text
    assert state_for_unique_id("sensor", f"{config_entry.entry_id}_{FUSED_KEY}").state == "70.5"


async def test_saved_filter_state_is_restored_instead_of_re_seeding(
    hass: HomeAssistant,
    hass_storage: dict[str, object],
    config_entry: MockConfigEntry,
    set_source: Callable[..., None],
    state_for_unique_id: Callable[[str, str], State],
) -> None:
    """A readable saved filter survives setup: the fused estimate comes from storage, not the raw readings."""
    set_source(SOURCE_ALPHA, "73")
    set_source(SOURCE_BETA, "73")
    config_entry.add_to_hass(hass)
    hass_storage[_store_key(config_entry.entry_id)] = {
        "version": 1,
        "data": {"sources": [SOURCE_ALPHA, SOURCE_BETA], "filter": _saved_filter_state(77.0, 73.0)},
    }

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    fused = float(state_for_unique_id("sensor", f"{config_entry.entry_id}_{FUSED_KEY}").state)
    assert fused == pytest.approx(75.0)
    bias_alpha = float(state_for_unique_id("sensor", f"{config_entry.entry_id}_{bias_entity_key(SOURCE_ALPHA)}").state)
    assert bias_alpha == pytest.approx(2.0)


async def test_saved_filter_state_is_reshaped_when_sources_swapped(
    hass: HomeAssistant,
    hass_storage: dict[str, object],
    config_entry: MockConfigEntry,
    set_source: Callable[..., None],
    state_for_unique_id: Callable[[str, str], State],
) -> None:
    """Restoring under a swapped source order remaps the learned biases to their sensors."""
    set_source(SOURCE_ALPHA, "73")
    set_source(SOURCE_BETA, "73")
    config_entry.add_to_hass(hass)
    # Saved with beta first, so the +2 bias belongs to beta; the entry lists alpha first.
    hass_storage[_store_key(config_entry.entry_id)] = {
        "version": 1,
        "data": {"sources": [SOURCE_BETA, SOURCE_ALPHA], "filter": _saved_filter_state(77.0, 73.0)},
    }

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    fused = float(state_for_unique_id("sensor", f"{config_entry.entry_id}_{FUSED_KEY}").state)
    assert fused == pytest.approx(75.0)
    bias_alpha = float(state_for_unique_id("sensor", f"{config_entry.entry_id}_{bias_entity_key(SOURCE_ALPHA)}").state)
    assert bias_alpha == pytest.approx(-2.0)
