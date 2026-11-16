"""Options flow for sensor_fusion."""

from typing import TYPE_CHECKING

from custom_components.sensor_fusion.const import CONF_BIAS_HORIZON, CONF_MAX_BIAS, CONF_SENSORS, CONF_VOLATILITY
from custom_components.sensor_fusion.coordinator import SensorFusionSettings
from homeassistant import config_entries

from .schemas import get_form_schema
from .validators import normalize_sources, validate_sources

if TYPE_CHECKING:
    from typing import Any


class SensorFusionOptionsFlow(config_entries.OptionsFlowWithReload):
    """
    Let the user change the fused sensors and tune the filter after setup.

    Options override the setup values for the same keys; the entry reloads, and the coordinator
    carries the learned biases of every kept sensor across the resize.
    """

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Show and process the options form.

        Returns:
            The form, or the stored options.

        """
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_SENSORS] = normalize_sources(user_input.get(CONF_SENSORS))
            errors = await validate_sources(self.hass, user_input[CONF_SENSORS])
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        settings = SensorFusionSettings.from_entry(self.config_entry)
        defaults = {
            CONF_SENSORS: list(settings.sources),
            CONF_VOLATILITY: settings.volatility,
            CONF_BIAS_HORIZON: settings.bias_horizon_minutes,
            CONF_MAX_BIAS: settings.max_bias,
        }

        return self.async_show_form(
            step_id="init",
            data_schema=get_form_schema(defaults if user_input is None else {**defaults, **user_input}),
            errors=errors,
        )


__all__ = ["SensorFusionOptionsFlow"]
