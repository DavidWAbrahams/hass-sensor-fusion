"""Constrained Kalman filter for fusing redundant Home Assistant sensors.

Pure math: only numpy and the standard library are imported here, so the filter is unit-testable
without Home Assistant. The coordinator owns event timing and delivery; this module owns the
state-space model described in docs/development/ARCHITECTURE.md.

State vector for N input sensors (dimension D = N + 1):

    x = [y, y_dot, b_0, ..., b_{N-2}]

``y`` is the fused estimate of the true value, ``y_dot`` its rate of change (which lets the filter
carry a trend through gaps between updates), and ``b_i`` the bias of sensor ``i`` against ``y``.
The bias of the last sensor is never stored: it is implied by the zero-sum constraint
``b_{N-1} = -sum(b_i)``, which removes the offset-versus-signal degeneracy without needing an
unbiased reference sensor.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Self

import numpy as np

SCHEMA_VERSION = 1

_MAX_DT_SECONDS = 30 * 24 * 3600.0
_EMA_ALPHA = 0.2
_WARMUP_SAMPLES = 3
_MIN_SIGMA_RATIO = 0.02
_SECONDS_PER_MINUTE = 60.0


@dataclass
class SensorTimingStats:
    """Per-sensor timing and noise history, persisted with the filter state."""

    last_update: float | None = None
    inter_arrival_ema: float | None = None
    innovation_var_ema: float | None = None
    reducible_var_ema: float | None = None
    samples: int = 0

    def to_dict(self) -> dict[str, float | int | None]:
        """
        Return the stats as JSON-serialisable values.

        Returns:
            The stats keyed by field name.

        """
        return {
            "last_update": self.last_update,
            "inter_arrival_ema": self.inter_arrival_ema,
            "innovation_var_ema": self.innovation_var_ema,
            "reducible_var_ema": self.reducible_var_ema,
            "samples": self.samples,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Self:
        """
        Rebuild the stats from stored values.

        Returns:
            The restored stats.

        """
        return cls(
            last_update=_as_float_or_none(data.get("last_update")),
            inter_arrival_ema=_as_float_or_none(data.get("inter_arrival_ema")),
            innovation_var_ema=_as_float_or_none(data.get("innovation_var_ema")),
            reducible_var_ema=_as_float_or_none(data.get("reducible_var_ema")),
            samples=_as_int(data.get("samples")),
        )


def _as_float_or_none(value: object) -> float | None:
    """
    Read a stored value as a float, tolerating None and anything not numeric.

    Returns:
        The value as a float, or None.

    """
    return float(value) if isinstance(value, (int, float)) else None


def _as_int(value: object) -> int:
    """
    Read a stored value as an int, defaulting non-numeric content to zero.

    Returns:
        The value as an int, or 0.

    """
    return value if isinstance(value, int) else 0


class KalmanFusionFilter:
    """Event-driven Kalman filter tracking the fused value, its trend and N - 1 sensor biases."""

    def __init__(
        self,
        *,
        num_sensors: int,
        volatility: float,
        bias_horizon_minutes: float,
        max_bias: float,
    ) -> None:
        """
        Create an unseeded filter for ``num_sensors`` inputs.

        Args:
            num_sensors: Number of fused sensors; the state tracks num_sensors - 1 biases.
            volatility: How fast the true signal changes, in signal units per root-minute. Scales
                the process noise on y and y_dot.
            bias_horizon_minutes: How quickly a sensor's bias may move to a new baseline; the
                per-sensor bias process noise is max_bias^2 per this many minutes.
            max_bias: Expected bound on a single sensor's deviation from the group mean, in signal
                units. Sets the initial bias covariance, the drift scale and the initial measurement
                variance.

        Raises:
            ValueError: If any parameter is outside its usable range.

        """
        if num_sensors < 2:
            raise ValueError("The fusion filter needs at least two sensors")
        if volatility <= 0 or bias_horizon_minutes <= 0 or max_bias <= 0:
            raise ValueError("volatility, bias_horizon_minutes and max_bias must be positive")

        self.num_sensors = num_sensors
        self._dim = num_sensors + 1
        self._max_bias = max_bias
        self._r0 = max_bias**2
        self._floor = (max_bias * _MIN_SIGMA_RATIO) ** 2 + 1e-12
        self._q_rw = volatility**2 / _SECONDS_PER_MINUTE
        # Constant white-noise-acceleration strength calibrated so y wanders by `volatility` over a
        # one-minute horizon, matching the user-facing units.
        self._q_acc = self._q_rw / (_SECONDS_PER_MINUTE**2 / 3)
        self._q_bias = self._r0 / (bias_horizon_minutes * _SECONDS_PER_MINUTE)

        self._x = np.zeros(self._dim)
        self._p = np.eye(self._dim) * self._r0
        self._p[1, 1] = self._q_acc * _SECONDS_PER_MINUTE
        self._last_time: float | None = None
        self._seeded = False
        self.stats: dict[int, SensorTimingStats] = {index: SensorTimingStats() for index in range(num_sensors)}

    def update_config(self, *, volatility: float, bias_horizon_minutes: float, max_bias: float) -> None:
        """
        Swap the noise parameters on a running filter, keeping the learned state.

        Args:
            volatility: New signal volatility in units per root-minute.
            bias_horizon_minutes: New bias adaptation horizon in minutes.
            max_bias: New expected bias bound in signal units.

        Raises:
            ValueError: If any parameter is outside its usable range.

        """
        if volatility <= 0 or bias_horizon_minutes <= 0 or max_bias <= 0:
            raise ValueError("volatility, bias_horizon_minutes and max_bias must be positive")
        self._max_bias = max_bias
        self._r0 = max_bias**2
        self._floor = (max_bias * _MIN_SIGMA_RATIO) ** 2 + 1e-12
        self._q_rw = volatility**2 / _SECONDS_PER_MINUTE
        self._q_acc = self._q_rw / (_SECONDS_PER_MINUTE**2 / 3)
        self._q_bias = self._r0 / (bias_horizon_minutes * _SECONDS_PER_MINUTE)

    @property
    def seeded(self) -> bool:
        """Return whether the filter has been seeded with at least one measurement."""
        return self._seeded

    @property
    def fused(self) -> float | None:
        """Return the current fused estimate of the true value, or None before seeding."""
        return float(self._x[0]) if self._seeded else None

    @property
    def trend(self) -> float | None:
        """Return the current rate-of-change estimate in units per second, or None before seeding."""
        return float(self._x[1]) if self._seeded else None

    @property
    def fused_variance(self) -> float:
        """Return the covariance's variance of the fused estimate, in squared signal units."""
        return float(self._p[0, 0])

    @property
    def last_update(self) -> float | None:
        """Return the timestamp of the last accepted measurement, or None."""
        return self._last_time

    def biases(self) -> list[float]:
        """
        Return the full bias vector, including the implied last sensor.

        Returns:
            One bias per sensor, summing to zero.

        """
        tracked = [float(self._x[2 + index]) for index in range(self.num_sensors - 1)]
        return [*tracked, -sum(tracked)]

    def bias_variance(self, index: int) -> float:
        """
        Return the covariance's variance of sensor ``index``'s bias, implied sensor included.

        Returns:
            The bias variance in squared signal units.

        """
        if index < self.num_sensors - 1:
            return float(self._p[2 + index, 2 + index])
        bias_block = self._p[2:, 2:]
        return float(np.ones(bias_block.shape[0]) @ bias_block @ np.ones(bias_block.shape[0]))

    def seed(self, measurements: Mapping[int, float]) -> None:
        """
        Seed the filter from simultaneous first readings of (a subset of) the sensors.

        Args:
            measurements: Sensor index to value for every input that already has a valid reading.

        """
        valid = {index: value for index, value in measurements.items() if np.isfinite(value)}
        if not valid:
            return
        self._x = np.zeros(self._dim)
        mean = float(np.mean(list(valid.values())))
        self._x[0] = mean
        for index, value in valid.items():
            if index < self.num_sensors - 1:
                self._x[2 + index] = value - mean
        self._p = np.eye(self._dim) * self._r0
        self._p[0, 0] = self._r0 / len(valid)
        self._p[1, 1] = self._q_acc * _SECONDS_PER_MINUTE
        self._seeded = True

    def step(self, index: int, value: float, timestamp: float) -> float:
        """
        Run one event-driven cycle: predict forward to ``timestamp``, then update on one sensor.

        Args:
            index: Slot of the sensor that just reported.
            value: The reported measurement.
            timestamp: Epoch seconds of the report.

        Returns:
            The fused estimate after the update.

        Raises:
            IndexError: If the sensor slot is unknown.
            ValueError: If the value is not finite.

        """
        if not 0 <= index < self.num_sensors:
            raise IndexError(f"Unknown sensor slot {index}")
        if not np.isfinite(value):
            raise ValueError("The measurement must be a finite number")

        if not self._seeded:
            self.seed({index: value})
        else:
            self.predict(timestamp - self._last_time if self._last_time is not None else 0.0)
        self._update(index, value)
        self._record_timing(index, value, timestamp)
        self._last_time = timestamp
        return self.fused  # type: ignore[return-value]  # seeded above, never None here

    def predict(self, dt: float) -> None:
        """
        Project state and covariance forward by ``dt`` seconds.

        Args:
            dt: Seconds since the last accepted measurement; clamped to [0, 30 days].

        """
        dt = min(max(dt, 0.0), _MAX_DT_SECONDS)
        if dt == 0.0:
            return
        transition = np.eye(self._dim)
        transition[0, 1] = dt
        process_noise = np.eye(self._dim) * (self._q_bias * dt)
        process_noise[0, 0] = self._q_acc * dt**3 / 3
        process_noise[0, 1] = self._q_acc * dt**2 / 2
        process_noise[1, 0] = self._q_acc * dt**2 / 2
        process_noise[1, 1] = self._q_acc * dt
        self._x = transition @ self._x
        self._p = transition @ self._p @ transition.T + process_noise

    def _observation(self, index: int) -> np.ndarray:
        """Return the observation row H_i mapping the state to this sensor's measurement."""
        row = np.zeros(self._dim)
        row[0] = 1.0
        if index < self.num_sensors - 1:
            row[2 + index] = 1.0
        else:
            row[2:] = -1.0
        return row

    def _update(self, index: int, value: float) -> None:
        """Run the single-sensor measurement update with the current R for this sensor."""
        observation = self._observation(index)
        measurement_var = self._measurement_variance(index)
        predicted_var = float(observation @ self._p @ observation)
        innovation_var = predicted_var + measurement_var
        innovation = value - float(observation @ self._x)
        gain = (self._p @ observation) / innovation_var
        self._x = self._x + gain * innovation
        residual = np.eye(self._dim) - np.outer(gain, observation)
        self._p = residual @ self._p @ residual.T + np.outer(gain, gain) * measurement_var
        self._p = (self._p + self._p.T) / 2
        self._update_noise_ema(index, innovation**2, predicted_var)

    def _measurement_variance(self, index: int) -> float:
        """
        Return R for one sensor: its identified noise inflated to offset its update rate.

        A sensor reporting k times more often would inject k times the information per unit time,
        so R is scaled by the reference inter-arrival interval over its own, where the reference is
        the median over sensors that have a measured interval. Only inflation is applied: a slower
        sensor keeps the base R.
        """
        stats = self.stats[index]
        if stats.samples >= _WARMUP_SAMPLES and stats.innovation_var_ema is not None:
            reducible = stats.reducible_var_ema or 0.0
            base = max(stats.innovation_var_ema - reducible, self._floor)
        else:
            base = self._r0
        known = [other.inter_arrival_ema for other in self.stats.values() if other.inter_arrival_ema]
        if stats.inter_arrival_ema and len(known) >= 2:
            scale = max(1.0, median(known) / stats.inter_arrival_ema)
        else:
            scale = 1.0
        return base * scale

    def _update_noise_ema(self, index: int, squared_innovation: float, predicted_var: float) -> None:
        """Fold this update's innovation and reducible variance into the sensor's running estimates."""
        stats = self.stats[index]
        if stats.innovation_var_ema is None:
            stats.innovation_var_ema = squared_innovation
            stats.reducible_var_ema = predicted_var
        else:
            stats.innovation_var_ema += _EMA_ALPHA * (squared_innovation - stats.innovation_var_ema)
            reducible = stats.reducible_var_ema or 0.0
            stats.reducible_var_ema = reducible + _EMA_ALPHA * (predicted_var - reducible)
        stats.samples += 1

    def _record_timing(self, index: int, value: float, timestamp: float) -> None:
        """Record the inter-arrival interval for this sensor; the first gap only stores the point."""
        stats = self.stats[index]
        if stats.last_update is not None:
            dt = min(max(timestamp - stats.last_update, 0.0), _MAX_DT_SECONDS)
            if stats.inter_arrival_ema is None:
                stats.inter_arrival_ema = dt
            else:
                stats.inter_arrival_ema += _EMA_ALPHA * (dt - stats.inter_arrival_ema)
        stats.last_update = timestamp

    def resize(self, keep: Sequence[int | None]) -> None:
        """
        Rebuild the filter for a changed sensor list, keeping learned biases.

        Args:
            keep: For every slot of the new list, the old slot to carry over, or None for a sensor
                that is new and starts with bias 0. Order defines the new slot order; the last
                entry is the sensor whose bias stays implicit. Remaining biases are re-centred by
                shifting y so every sensor's implied measurement prediction is unchanged and the
                zero-sum constraint holds for the new sensor count.

        Raises:
            ValueError: If fewer than two slots are kept, or an old slot is repeated or unknown.

        """
        new_num = len(keep)
        if new_num < 2:
            raise ValueError("The fusion filter needs at least two sensors")
        kept_old = [old for old in keep if old is not None]
        if len(set(kept_old)) != len(kept_old) or any(not 0 <= old < self.num_sensors for old in kept_old):
            raise ValueError("keep must contain distinct old slots")

        transform = np.zeros((new_num + 1, self._dim))
        transform[1, 1] = 1.0

        def bias_row(old: int) -> np.ndarray:
            row = np.zeros(self._dim)
            if old < self.num_sensors - 1:
                row[2 + old] = 1.0
            else:
                row[2:] = -1.0
            return row

        # Re-centring divides by the number of carried-over sensors, not the new count, so the
        # prediction of every kept sensor survives even when new slots are mixed in.
        centre = np.zeros(self._dim)
        for old in kept_old:
            centre += bias_row(old)
        centre /= len(kept_old)

        transform[0, 0] = 1.0
        transform[0] += centre
        for slot, old in enumerate(keep[: new_num - 1]):
            if old is not None:
                transform[2 + slot] = bias_row(old)
            transform[2 + slot] -= centre

        self._x = transform @ self._x
        self._p = transform @ self._p @ transform.T
        self._p = (self._p + self._p.T) / 2

        # A brand-new tracked slot must start unbiased with full prior variance, uncorrelated with
        # everything else; the transform row above only yields the re-centring term.
        for slot, old in enumerate(keep[: new_num - 1]):
            if old is None:
                self._p[2 + slot, :] = 0.0
                self._p[:, 2 + slot] = 0.0
                self._p[2 + slot, 2 + slot] = self._r0

        old_stats = self.stats
        self.stats = {}
        for slot, old in enumerate(keep):
            self.stats[slot] = old_stats[old] if old is not None else SensorTimingStats()

        self.num_sensors = new_num
        self._dim = new_num + 1

    def to_dict(self) -> dict[str, object]:
        """
        Serialise the full filter state for persistence.

        Returns:
            A JSON-serialisable dict with the state vector, covariance, timing stats and config.

        """
        return {
            "version": SCHEMA_VERSION,
            "last_time": self._last_time,
            "seeded": self._seeded,
            "config": {
                "num_sensors": self.num_sensors,
                "q_acc": self._q_acc,
                "q_bias": self._q_bias,
                "r0": self._r0,
                "floor": self._floor,
            },
            "x": self._x.tolist(),
            "P": self._p.tolist(),
            "stats": {str(index): stats.to_dict() for index, stats in self.stats.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Self:
        """
        Restore a filter saved by to_dict.

        Returns:
            The restored filter.

        Raises:
            ValueError: If the payload has an unknown version or inconsistent dimensions.

        """
        if data.get("version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported filter state version {data.get('version')!r}")
        config = data["config"]
        assert isinstance(config, Mapping)
        filter_obj = cls(
            num_sensors=int(config["num_sensors"]),
            volatility=1.0,
            bias_horizon_minutes=1.0,
            max_bias=1.0,
        )
        filter_obj._q_acc = float(config["q_acc"])
        filter_obj._q_bias = float(config["q_bias"])
        filter_obj._r0 = float(config["r0"])
        filter_obj._floor = float(config["floor"])

        state = np.asarray(data["x"], dtype=float)
        covariance = np.asarray(data["P"], dtype=float)
        expected = filter_obj.num_sensors + 1
        if state.shape != (expected,) or covariance.shape != (expected, expected):
            raise ValueError("Saved filter dimensions do not match the saved sensor count")
        filter_obj._x = state
        filter_obj._p = covariance
        filter_obj._last_time = _as_float_or_none(data.get("last_time"))
        filter_obj._seeded = bool(data.get("seeded", False))
        raw_stats = data["stats"]
        assert isinstance(raw_stats, Mapping)
        filter_obj.stats = {
            index: SensorTimingStats.from_dict(raw_stats[str(index)])
            for index in range(filter_obj.num_sensors)
            if str(index) in raw_stats
        }
        for index in range(filter_obj.num_sensors):
            filter_obj.stats.setdefault(index, SensorTimingStats())
        return filter_obj


__all__ = ["SCHEMA_VERSION", "KalmanFusionFilter", "SensorTimingStats"]
