"""Validation of the fusion source selection."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def normalize_sources(value: object) -> list[str]:
    """
    Return the submitted sensor selection as a list of entity ids.

    Args:
        value: The CONF_SENSORS value from a form, a list or a single entity id.

    Returns:
        The entity ids, order preserved.

    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(entity_id) for entity_id in value]
    return []


async def validate_sources(hass: HomeAssistant, sources: list[str]) -> dict[str, str]:
    """
    Check the selection is usable: at least two sensors whose readings share units.

    Sensors without a state yet are accepted — an entity may be added later — but sensors that do
    exist must agree on unit and device class, or their readings cannot be fused.

    Args:
        hass: The running Home Assistant instance.
        sources: The chosen source entity ids.

    Returns:
        An empty dict when the selection is valid, else the form error keys.

    """
    if len(set(sources)) < 2:
        return {"base": "not_enough_sensors"}
    fingerprints = {
        (state.attributes.get(ATTR_UNIT_OF_MEASUREMENT), state.attributes.get(ATTR_DEVICE_CLASS))
        for state in (hass.states.get(entity_id) for entity_id in sources)
        if state is not None
    }
    if len(fingerprints) > 1:
        return {"base": "mismatched_sources"}
    return {}


__all__ = ["normalize_sources", "validate_sources"]
