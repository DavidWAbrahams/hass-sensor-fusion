"""Constants for sensor_fusion."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "sensor_fusion"

CONF_SENSORS = "sensors"
CONF_VOLATILITY = "volatility"
CONF_BIAS_HORIZON = "bias_horizon_minutes"
CONF_MAX_BIAS = "max_bias"

DEFAULT_VOLATILITY = 2.0
DEFAULT_BIAS_HORIZON = 480.0
DEFAULT_MAX_BIAS = 10.0
