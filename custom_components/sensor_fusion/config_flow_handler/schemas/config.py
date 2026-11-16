"""Probatio schemas for the setup and options forms."""

from collections.abc import Mapping
from typing import Any

import probatio

from custom_components.sensor_fusion.const import (
    CONF_BIAS_HORIZON,
    CONF_MAX_BIAS,
    CONF_SENSORS,
    CONF_VOLATILITY,
    DEFAULT_BIAS_HORIZON,
    DEFAULT_MAX_BIAS,
    DEFAULT_VOLATILITY,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

_SENSORS_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", multiple=True),
)


def _number(minimum: float, maximum: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    """Return a box number selector bounded to a usable parameter range."""
    config = {"min": minimum, "max": maximum, "step": step, "mode": selector.NumberSelectorMode.BOX}
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def get_form_schema(defaults: Mapping[str, Any] | None = None) -> probatio.Schema:
    """
    Build the schema shared by the user and options forms.

    Args:
        defaults: Current values used to pre-fill the form; the name field is omitted.

    Returns:
        The probatio schema for the fusion parameters.

    """
    defaults = defaults or {}
    schema_dict: dict[Any, Any] = {}
    if CONF_NAME in defaults:
        schema_dict[probatio.Required(CONF_NAME, default=defaults[CONF_NAME])] = selector.TextSelector()
    schema_dict.update(
        {
            probatio.Required(CONF_SENSORS, default=defaults.get(CONF_SENSORS, probatio.UNDEFINED)): (
                _SENSORS_SELECTOR
            ),
            probatio.Optional(CONF_VOLATILITY, default=DEFAULT_VOLATILITY): _number(0.01, 1000.0, 0.01),
            probatio.Optional(CONF_BIAS_HORIZON, default=DEFAULT_BIAS_HORIZON): _number(1.0, 43200.0, 1.0, "min"),
            probatio.Optional(CONF_MAX_BIAS, default=DEFAULT_MAX_BIAS): _number(0.01, 1000.0, 0.01),
        },
    )
    return probatio.Schema(schema_dict)


def get_user_schema(defaults: Mapping[str, Any] | None = None) -> probatio.Schema:
    """
    Build the schema for the user step.

    Args:
        defaults: Previously submitted values, used to pre-fill the form.

    Returns:
        The probatio schema including the instance name.

    """
    return get_form_schema({CONF_NAME: "", **(defaults or {})})


__all__ = ["get_form_schema", "get_user_schema"]
