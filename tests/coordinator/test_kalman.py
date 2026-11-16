"""Tests for the constrained Kalman fusion engine.

The engine is pure math with no Home Assistant imports, so these tests drive it directly with
synthetic event streams instead of going through ``hass.states``.

Note the identifiability the zero-sum constraint imposes: with no unbiased reference sensor, a
common offset shared by every input is indistinguishable from the signal itself. The filter
therefore converges to ``y = truth + mean(offsets)`` and ``b_i = offset_i - mean(offsets)``, and
tests assert against that, not against the raw offsets.
"""

from collections.abc import Callable, Sequence

import pytest

from custom_components.sensor_fusion.coordinator.kalman import KalmanFusionFilter

pytestmark = pytest.mark.unit


def _constant(_time: float) -> float:
    """Return a fixed true value."""
    return 65.0


def _ramp(time: float) -> float:
    """Return a true value rising one unit per minute."""
    return 60.0 + time / 60.0


def _fused(filter_obj: KalmanFusionFilter) -> float:
    """Read the fused estimate, asserting the filter is seeded."""
    fused = filter_obj.fused
    assert fused is not None
    return fused


def _run_scenario(
    *,
    offsets: Sequence[float],
    intervals: Sequence[float],
    duration: float,
    bias_horizon_minutes: float,
    volatility: float = 1.0,
    max_bias: float = 10.0,
    truth: Callable[[float], float] = _constant,
    jumps: Sequence[tuple[int, float, float]] | None = None,
) -> KalmanFusionFilter:
    """
    Drive a filter with a seeded first round and interleaved events until ``duration``.

    Args:
        offsets: Each sensor's fixed bias against the truth.
        intervals: Each sensor's update interval in seconds.
        duration: Simulated seconds to run.
        bias_horizon_minutes: Filter bias horizon parameter.
        volatility: Filter volatility parameter.
        max_bias: Filter max bias parameter.
        truth: True value as a function of simulated time.
        jumps: Optional (sensor, amount, time) steps added to that sensor's offset from ``time``.

    Returns:
        The filter at the end of the run.

    """
    steps = list(jumps) if jumps is not None else []
    filter_obj = KalmanFusionFilter(
        num_sensors=len(offsets),
        volatility=volatility,
        bias_horizon_minutes=bias_horizon_minutes,
        max_bias=max_bias,
    )

    def reading(index: int, time: float) -> float:
        step = sum(amount for sensor, amount, when in steps if sensor == index and time >= when)
        return truth(time) + offsets[index] + step

    filter_obj.seed({index: reading(index, 0.0) for index in range(len(offsets))})
    next_update = list(intervals)
    time = 0.0
    while time < duration:
        index = min(range(len(offsets)), key=next_update.__getitem__)
        time = next_update[index]
        filter_obj.step(index, reading(index, time), time)
        next_update[index] += intervals[index]
    return filter_obj


@pytest.mark.parametrize(
    ("num_sensors", "volatility", "bias_horizon_minutes", "max_bias"),
    [
        pytest.param(1, 1.0, 60.0, 5.0, id="one-sensor"),
        pytest.param(2, 0.0, 60.0, 5.0, id="zero-volatility"),
        pytest.param(2, 1.0, 0.0, 5.0, id="zero-horizon"),
        pytest.param(2, 1.0, 60.0, -1.0, id="negative-max-bias"),
    ],
)
def test_constructor_rejects_bad_parameters(
    num_sensors: int,
    volatility: float,
    bias_horizon_minutes: float,
    max_bias: float,
) -> None:
    """Parameters outside their usable range raise at construction."""
    with pytest.raises(ValueError, match="at least two|positive"):
        KalmanFusionFilter(
            num_sensors=num_sensors,
            volatility=volatility,
            bias_horizon_minutes=bias_horizon_minutes,
            max_bias=max_bias,
        )


def test_seed_with_a_subset_uses_only_finite_values() -> None:
    """Seeding skips non-finite readings and treats the rest as simultaneous."""
    filter_obj = KalmanFusionFilter(num_sensors=3, volatility=1.0, bias_horizon_minutes=60.0, max_bias=5.0)
    filter_obj.seed({0: float("nan"), 1: 70.0, 2: 60.0})

    assert filter_obj.seeded
    assert _fused(filter_obj) == pytest.approx(65.0)
    assert filter_obj.biases() == pytest.approx([0.0, 5.0, -5.0])


def test_seed_without_any_valid_value_leaves_the_filter_unseeded() -> None:
    """An empty or all-NaN seed does not mark the filter as started."""
    filter_obj = KalmanFusionFilter(num_sensors=2, volatility=1.0, bias_horizon_minutes=60.0, max_bias=5.0)
    filter_obj.seed({})
    filter_obj.seed({0: float("inf")})

    assert not filter_obj.seeded
    assert filter_obj.fused is None
    assert filter_obj.trend is None


def test_first_step_seeds_the_filter() -> None:
    """A first measurement with no seed initialises the state around that measurement."""
    filter_obj = KalmanFusionFilter(num_sensors=2, volatility=1.0, bias_horizon_minutes=60.0, max_bias=5.0)
    fused = filter_obj.step(1, 62.0, 1000.0)

    assert filter_obj.seeded
    assert fused == pytest.approx(62.0, abs=1.0)
    assert filter_obj.last_update == 1000.0


@pytest.mark.parametrize(
    ("index", "value"),
    [
        pytest.param(3, 60.0, id="unknown-slot"),
        pytest.param(-1, 60.0, id="negative-slot"),
        pytest.param(0, float("nan"), id="nan"),
        pytest.param(0, float("inf"), id="inf"),
    ],
)
def test_step_rejects_bad_slots_and_values(index: int, value: float) -> None:
    """An out-of-range slot or a non-finite value is refused, leaving the filter usable."""
    filter_obj = KalmanFusionFilter(num_sensors=3, volatility=1.0, bias_horizon_minutes=60.0, max_bias=5.0)
    filter_obj.seed({0: 60.0, 1: 60.0, 2: 60.0})
    before = _fused(filter_obj)

    with pytest.raises((IndexError, ValueError)):
        filter_obj.step(index, value, 1000.0)

    assert _fused(filter_obj) == pytest.approx(before)


def test_clean_consistent_sensors_stay_on_the_true_value() -> None:
    """Three noise-free sensors agreeing on a constant keep the estimate exactly there."""
    filter_obj = _run_scenario(
        offsets=(0.0, 0.0, 0.0),
        intervals=(300.0, 300.0, 300.0),
        duration=24 * 3600.0,
        bias_horizon_minutes=240.0,
    )

    assert _fused(filter_obj) == pytest.approx(65.0, abs=1e-3)
    assert filter_obj.biases() == pytest.approx([0.0, 0.0, 0.0], abs=1e-3)
    # The variance settles at the process-noise/measurement-noise balance of the model - bias
    # process noise keeps injecting uncertainty - bounded and far below the max_bias^2 prior.
    assert 0.0 < filter_obj.fused_variance < 5.0


def test_biases_converge_to_the_true_offsets() -> None:
    """Offsets of +5, -2 and -3 bpm (already zero-mean) separate out of the fused value."""
    filter_obj = _run_scenario(
        offsets=(5.0, -2.0, -3.0),
        intervals=(600.0, 900.0, 1800.0),
        duration=6 * 3600.0,
        bias_horizon_minutes=240.0,
    )

    biases = filter_obj.biases()
    assert biases == pytest.approx([5.0, -2.0, -3.0], abs=0.5)
    assert sum(biases) == pytest.approx(0.0, abs=1e-9)
    assert _fused(filter_obj) == pytest.approx(65.0, abs=0.5)


def test_a_frequent_biased_sensor_does_not_drag_the_estimate() -> None:
    """A sensor reporting 30x more often with +5 off is absorbed, y staying near the group mean."""
    filter_obj = _run_scenario(
        offsets=(5.0, 0.0, 0.0),
        intervals=(60.0, 1800.0, 1800.0),
        duration=6 * 3600.0,
        bias_horizon_minutes=7 * 24 * 60,
    )

    # With the bias horizon long enough to keep the seeded biases nearly frozen, the fused value
    # tracks the information-rate-weighted mean; without rate inflation the fast sensor alone
    # would pull it to ~69.7.
    assert _fused(filter_obj) == pytest.approx(65.0 + 5.0 / 3.0, abs=1.0)


def test_short_bias_horizon_adapts_to_a_new_offset() -> None:
    """A five bpm offset jumping onto one sensor is absorbed into its bias within hours."""
    # Zero-sum splits the identified offset as +2/5 of it against -1/5 each on the clean sensors.
    filter_obj = _run_scenario(
        offsets=(0.0, 0.0, 0.0),
        intervals=(600.0, 1200.0, 1800.0),
        duration=8 * 3600.0,
        bias_horizon_minutes=60.0,
        jumps=((2, 5.0, 2 * 3600.0),),
    )

    biases = filter_obj.biases()
    assert biases[2] == pytest.approx(10.0 / 3.0, abs=1.0)
    assert biases[0] == pytest.approx(-5.0 / 3.0, abs=0.7)
    assert biases[1] == pytest.approx(-5.0 / 3.0, abs=0.7)


def test_bias_horizon_scales_the_bias_process_noise() -> None:
    """Over one hour a one-hour horizon admits max_bias^2 of bias freedom, a month-long one 24x less."""
    short = KalmanFusionFilter(num_sensors=2, volatility=1.0, bias_horizon_minutes=60.0, max_bias=10.0)
    long = KalmanFusionFilter(num_sensors=2, volatility=1.0, bias_horizon_minutes=24 * 60.0, max_bias=10.0)
    short.seed({0: 60.0, 1: 62.0})
    long.seed({0: 60.0, 1: 62.0})

    short.predict(3600.0)
    long.predict(3600.0)

    # Seeded P_bias is max_bias^2 = 100 for both; predict adds exactly q_bias * dt on top.
    assert short.bias_variance(0) == pytest.approx(200.0)
    assert long.bias_variance(0) == pytest.approx(100.0 + 100.0 / 24.0)


def test_coasting_through_an_outage_holds_the_state_and_grows_uncertainty() -> None:
    """Predicting six hours with no data keeps state and biases and only widens the covariance."""
    filter_obj = _run_scenario(
        offsets=(4.0, -1.0, 2.0, -5.0),
        intervals=(600.0, 900.0, 1200.0, 1800.0),
        duration=4 * 3600.0,
        bias_horizon_minutes=240.0,
    )
    fused = _fused(filter_obj)
    biases = filter_obj.biases()
    variance_before = filter_obj.fused_variance
    bias_variance_before = filter_obj.bias_variance(1)

    filter_obj.predict(6 * 3600.0)

    assert _fused(filter_obj) == pytest.approx(fused)
    assert filter_obj.biases() == pytest.approx(biases)
    assert filter_obj.fused_variance > variance_before
    assert filter_obj.bias_variance(1) > bias_variance_before

    # The constant signal means the next update, with zero innovation, moves nothing either.
    assert filter_obj.step(0, 65.0 + biases[0], 10 * 3600.0) == pytest.approx(fused, abs=1e-4)


def test_trend_carries_the_estimate_through_a_gap() -> None:
    """A learned one-unit-per-minute ramp keeps projecting through a 15-minute gap instead of freezing."""
    filter_obj = _run_scenario(
        offsets=(0.0, 0.0),
        intervals=(300.0, 300.0),
        duration=4 * 3600.0,
        bias_horizon_minutes=240.0,
        volatility=2.0,
        truth=_ramp,
    )
    frozen = _fused(filter_obj)

    filter_obj.predict(900.0)
    coasted = _fused(filter_obj)

    # Without a trend the gap alone costs 15 units; trend + process noise should hold most of it.
    assert coasted == pytest.approx(_ramp(4 * 3600.0 + 900.0), abs=2.0)
    assert coasted > frozen + 10.0


def test_resize_remove_recentres_without_moving_predictions() -> None:
    """Dropping a sensor shifts y and the remaining biases so every prediction and zero-sum hold."""
    filter_obj = _run_scenario(
        offsets=(5.0, 0.0, -5.0, -7.0),
        intervals=(600.0, 900.0, 1200.0, 1800.0),
        duration=2 * 3600.0,
        bias_horizon_minutes=240.0,
    )
    predictions = [_fused(filter_obj) + bias for bias in filter_obj.biases()]
    assert predictions[0] == pytest.approx(70.0, abs=0.5)
    assert predictions[3] == pytest.approx(58.0, abs=0.5)

    filter_obj.resize([0, 2, 3])

    biases = filter_obj.biases()
    fused = _fused(filter_obj)
    assert filter_obj.num_sensors == 3
    assert fused + biases[0] == pytest.approx(predictions[0], abs=1e-9)
    assert fused + biases[1] == pytest.approx(predictions[2], abs=1e-9)
    assert fused + biases[2] == pytest.approx(predictions[3], abs=1e-9)
    assert sum(biases) == pytest.approx(0.0, abs=1e-9)


def test_resize_add_starts_a_new_sensor_unbiased_with_full_prior() -> None:
    """A slot with no predecessor gets bias zero and the full max-bias variance, uncorrelated."""
    filter_obj = _run_scenario(
        offsets=(5.0, 0.0, -5.0),
        intervals=(600.0, 900.0, 1800.0),
        duration=2 * 3600.0,
        bias_horizon_minutes=240.0,
    )
    predictions = [_fused(filter_obj) + bias for bias in filter_obj.biases()]

    filter_obj.resize([0, None, 2])

    biases = filter_obj.biases()
    fused = _fused(filter_obj)
    assert filter_obj.num_sensors == 3
    assert biases[1] == pytest.approx(0.0)
    assert filter_obj.bias_variance(1) == pytest.approx(100.0)
    assert fused + biases[0] == pytest.approx(predictions[0], abs=1e-9)
    assert fused + biases[2] == pytest.approx(predictions[2], abs=1e-9)


@pytest.mark.parametrize(
    "keep",
    [
        pytest.param([0], id="below-two"),
        pytest.param([0, 0, 1], id="repeated-slot"),
        pytest.param([0, 7], id="unknown-slot"),
    ],
)
def test_resize_rejects_invalid_keep(keep: list[int]) -> None:
    """A keep list that cannot describe the new sensor set is refused."""
    filter_obj = KalmanFusionFilter(num_sensors=3, volatility=1.0, bias_horizon_minutes=60.0, max_bias=5.0)
    filter_obj.seed({0: 60.0, 1: 62.0, 2: 58.0})

    with pytest.raises(ValueError, match="at least two|distinct"):
        filter_obj.resize(keep)


def test_serialisation_round_trip_preserves_everything() -> None:
    """A saved filter restored from its dict continues bit-for-bit identically."""
    filter_obj = _run_scenario(
        offsets=(4.0, -1.0, -3.0),
        intervals=(600.0, 900.0, 1800.0),
        duration=3 * 3600.0,
        bias_horizon_minutes=240.0,
    )
    restored = KalmanFusionFilter.from_dict(filter_obj.to_dict())

    assert restored.num_sensors == filter_obj.num_sensors
    assert restored.fused == pytest.approx(filter_obj.fused)
    assert restored.trend == pytest.approx(filter_obj.trend)
    assert restored.biases() == pytest.approx(filter_obj.biases())
    assert restored.fused_variance == pytest.approx(filter_obj.fused_variance)
    assert [restored.bias_variance(index) for index in range(3)] == pytest.approx(
        [filter_obj.bias_variance(index) for index in range(3)]
    )
    assert restored.last_update == filter_obj.last_update
    assert {index: stats.to_dict() for index, stats in restored.stats.items()} == {
        index: stats.to_dict() for index, stats in filter_obj.stats.items()
    }

    for filter_copy in (filter_obj, restored):
        filter_copy.predict(60.0)
    assert restored.step(0, 70.0, 4 * 3600.0) == pytest.approx(filter_obj.step(0, 70.0, 4 * 3600.0), rel=0, abs=1e-12)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda saved: saved.__setitem__("version", 999), id="unknown-version"),
        pytest.param(lambda saved: saved.__setitem__("x", [0.0, 0.0]), id="wrong-dimensions"),
    ],
)
def test_from_dict_rejects_corrupt_state(mutate: Callable[[dict[str, object]], None]) -> None:
    """A payload with a future schema version or inconsistent shapes fails loudly."""
    filter_obj = KalmanFusionFilter(num_sensors=2, volatility=1.0, bias_horizon_minutes=60.0, max_bias=5.0)
    filter_obj.seed({0: 60.0, 1: 62.0})
    saved = filter_obj.to_dict()
    mutate(saved)

    with pytest.raises(ValueError, match="version|dimensions"):
        KalmanFusionFilter.from_dict(saved)


def test_absurd_gaps_are_clamped_and_keep_the_covariance_finite() -> None:
    """A century-long or negative gap cannot blow the covariance up or send time backwards."""
    filter_obj = KalmanFusionFilter(num_sensors=2, volatility=1.0, bias_horizon_minutes=60.0, max_bias=5.0)
    filter_obj.seed({0: 60.0, 1: 60.0})

    filter_obj.predict(100.0 * 365.0 * 24 * 3600.0)
    filter_obj.predict(-10.0)

    # 30 days of constant-acceleration noise on a 1 unit/rt-min signal is large but bounded.
    assert 1e10 < filter_obj.fused_variance < 1e16
