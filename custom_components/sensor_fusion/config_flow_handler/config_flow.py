"""Config flow for sensor_fusion — user setup."""

from typing import TYPE_CHECKING

from custom_components.sensor_fusion.const import CONF_SENSORS, DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.loader import async_get_loaded_integration

from .options_flow import SensorFusionOptionsFlow
from .schemas import get_user_schema
from .validators import normalize_sources, validate_sources

if TYPE_CHECKING:
    from typing import Any


class SensorFusionConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Handle the config flow for sensor_fusion.

    A fusion instance has no identity beyond what the user chooses, so the flow sets no unique ID:
    several independent instances are a normal configuration, and nothing identifies "the same"
    instance across setups to deduplicate against.
    """

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SensorFusionOptionsFlow:
        """
        Return the options flow for this handler.

        Returns:
            The options flow instance.

        """
        return SensorFusionOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Handle a flow started by the user.

        Returns:
            The form, or the created config entry.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_SENSORS] = normalize_sources(user_input.get(CONF_SENSORS))
            errors = await validate_sources(self.hass, user_input[CONF_SENSORS])
            if not errors:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or "Sensor Fusion",
                    data=user_input,
                )

        integration = async_get_loaded_integration(self.hass, DOMAIN)

        return self.async_show_form(
            step_id="user",
            data_schema=get_user_schema(user_input),
            errors=errors,
            description_placeholders={
                "documentation_url": integration.documentation or "",
            },
        )


__all__ = ["SensorFusionConfigFlowHandler"]
