import math

import numpy as np
import pytest

from minispice import CircuitError, NetlistError, parse
from minispice.analysis.transient import transient
from minispice.components.waveforms import PiecewiseLinear, Pulse, Sine

RC = "V1 1 0 STEP(0 5 0)\nR1 1 2 1k\nC1 2 0 1u"  # τ = RC = 1 ms
RLC = "V1 1 0 STEP(0 1 0)\nR1 1 2 10\nL1 2 3 1m\nC1 3 0 1u"


def exact_rc(t):
    return 5 * (1 - np.exp(-t / 1e-3))


# ---- Phase 7: backward Euler -----------------------------------------------------------------

def test_hand_check_rc_one_time_constant():
    """Phase 7 hand check: after one time constant the capacitor is at 1 - 1/e = 63.2 % of the source."""
    r = transient(parse(RC), 5e-3, 1e-5, method="be", adaptive=False)
    assert r.at("v(2)", 1e-3) / 5 == pytest.approx(1 - math.exp(-1), rel=5e-3)


def test_rc_whole_curve_matches_formula():
    r = transient(parse(RC), 5e-3, 1e-5, method="be", adaptive=False)
    assert np.max(np.abs(r.v(2) - exact_rc(r.times))) < 0.01  # within 10 mV of 5 V everywhere


def test_smaller_steps_are_more_accurate():
    errors = []
    for step in (1e-4, 1e-5, 1e-6):
        r = transient(parse(RC), 3e-3, step, method="be", adaptive=False)
        errors.append(np.max(np.abs(r.v(2) - exact_rc(r.times))))
    assert errors[0] > errors[1] > errors[2]
    # Backward Euler is first order: 10x smaller steps give about 10x smaller error.
    assert errors[0] / errors[1] == pytest.approx(10, rel=0.3)


def test_capacitor_current_and_energy():
    r = transient(parse(RC), 5e-3, 1e-6, method="be", adaptive=False)
    # i = C dv/dt: starts at 5 V / 1k = 5 mA and decays.
    assert r.i("C1")[1] == pytest.approx(5e-3, rel=0.01)
    # Energy stored at the end is ½ C V², and the source delivered twice that (half is burned in R1).
    v_end = r.v(2)[-1]
    assert r.energy("C1") == pytest.approx(0.5 * 1e-6 * v_end ** 2, rel=0.01)
    assert -r.energy("V1") == pytest.approx(2 * 0.5 * 1e-6 * v_end ** 2, rel=0.02)


def test_inductor_current_rises_with_time_constant_l_over_r():
    r = transient(parse("V1 1 0 STEP(0 1 0)\nR1 1 2 100\nL1 2 0 10m"), 1e-3, 1e-6)
    tau = 10e-3 / 100
    assert r.at("i(L1)", tau) == pytest.approx(0.01 * (1 - math.exp(-1)), rel=1e-3)


def test_pulse_source_drives_circuit():
    r = transient(parse("V1 1 0 PULSE(0 1 1m 0 0 1m 4m)\nR1 1 0 1k"), 6e-3, 1e-5)
    assert r.at("v(1)", 0.5e-3) == pytest.approx(0)
    assert r.at("v(1)", 1.5e-3) == pytest.approx(1)
    assert r.at("v(1)", 3e-3) == pytest.approx(0)
    assert r.at("v(1)", 5.5e-3) == pytest.approx(1)  # the next period


def test_starting_point_is_dc_solution():
    # With a plain DC source, the capacitor starts already charged (that's the DC operating point).
    r = transient(parse("V1 1 0 5\nR1 1 2 1k\nC1 2 0 1u"), 1e-3, 1e-5)
    assert r.v(2)[0] == pytest.approx(5)
    assert np.allclose(r.v(2), 5)


def test_uic_and_initial_conditions():
    r = transient(parse("R1 1 0 1k\nC1 1 0 1u ic=5"), 2e-3, 1e-5, uic=True)
    assert r.at("v(1)", 1e-3) == pytest.approx(5 * math.exp(-1), rel=2e-3)


def test_dot_ic_holds_node_during_dc_solve():
    circuit = parse("V1 1 0 5\nR1 1 2 1k\nC1 2 0 1u\n.ic v(2)=0")
    r = transient(circuit, 5e-3, 1e-5)
    assert r.v(2)[0] == pytest.approx(0, abs=1e-3)
    assert r.at("v(2)", 1e-3) == pytest.approx(5 * (1 - math.exp(-1)), rel=5e-3)


# ---- Phase 8: trapezoidal and adaptive steps ----------------------------------------------------

def test_trapezoidal_is_more_accurate_than_backward_euler():
    be = transient(parse(RC), 3e-3, 1e-4, method="be", adaptive=False)
    trap = transient(parse(RC), 3e-3, 1e-4, method="trap", adaptive=False)
    err_be = np.max(np.abs(be.v(2) - exact_rc(be.times)))
    err_trap = np.max(np.abs(trap.v(2) - exact_rc(trap.times)))
    assert err_trap < err_be / 10


def test_adaptive_step_is_accurate_and_uses_small_steps_only_where_needed():
    r = transient(parse(RC), 10e-3, 1e-4)
    assert np.max(np.abs(r.v(2) - exact_rc(r.times))) < 5e-3
    steps = np.diff(r.times)
    # Small steps right after the step input, and the largest allowed step once things settle.
    assert steps[0] < steps.max() / 10
    assert steps.max() == pytest.approx(1e-4)


def _ringing(r):
    """Zero crossings and peaks of the ringing around the final value of 1 V."""
    s = r.v(3) - 1.0
    t = r.times
    idx = np.nonzero(np.diff(np.sign(s)))[0]
    crossings = t[idx] - s[idx] * (t[idx + 1] - t[idx]) / (s[idx + 1] - s[idx])
    return crossings


def test_hand_check_rlc_rings_at_natural_frequency():
    """Phase 8 hand check: rings at about 1/(2π√(LC)) = 5.03 kHz.

    Precisely, the damped frequency is √(ω0² - α²)/2π with α = R/(2L), which is 4.97 kHz.
    """
    r = transient(parse(RLC), 2e-3, 1e-6)
    crossings = _ringing(r)
    measured = 1 / (2 * np.mean(np.diff(crossings)))
    w0 = 1 / math.sqrt(1e-3 * 1e-6)
    alpha = 10 / (2 * 1e-3)
    assert measured == pytest.approx(w0 / (2 * math.pi), rel=0.02)
    assert measured == pytest.approx(math.sqrt(w0 ** 2 - alpha ** 2) / (2 * math.pi), rel=1e-3)


def _envelope_ratio(r, alpha):
    """Measured decay of the ringing over 1 ms, against the textbook e^(-α t)."""
    s = np.abs(r.v(3) - 1.0)
    early = (r.times > 0.1e-3) & (r.times < 0.3e-3)
    late = (r.times > 1.1e-3) & (r.times < 1.3e-3)
    return (s[late].max() / s[early].max()) / math.exp(-alpha * 1e-3)


def test_decay_matches_textbook_with_trapezoidal():
    r = transient(parse(RLC), 2e-3, 1e-6)
    assert _envelope_ratio(r, 5000) == pytest.approx(1.0, rel=0.03)


def test_backward_euler_damps_oscillations_too_much():
    """Backward Euler loses energy every step, so ringing dies out faster than in reality."""
    be = transient(parse(RLC), 2e-3, 5e-6, method="be", adaptive=False)
    trap = transient(parse(RLC), 2e-3, 5e-6, method="trap", adaptive=False)
    assert _envelope_ratio(be, 5000) < 0.6
    assert _envelope_ratio(trap, 5000) == pytest.approx(1.0, rel=0.05)


def test_sine_source():
    r = transient(parse("V1 1 0 SIN(0 2 1k)\nR1 1 0 1k"), 2e-3, 1e-6)
    assert r.at("v(1)", 0.25e-3) == pytest.approx(2, rel=1e-3)
    assert r.at("v(1)", 0.75e-3) == pytest.approx(-2, rel=1e-3)


def test_pwl_source():
    r = transient(parse("V1 1 0 PWL(0 0 1m 1 2m 1 3m 0)\nR1 1 0 1k"), 4e-3, 1e-5)
    assert r.at("v(1)", 0.5e-3) == pytest.approx(0.5, rel=1e-3)
    assert r.at("v(1)", 1.5e-3) == pytest.approx(1)
    assert r.at("v(1)", 3.5e-3) == pytest.approx(0)


@pytest.mark.parametrize("wave, t, expected", [
    (Pulse([0, 5, 1, 1, 1, 2, 10]), 0.5, 0), (Pulse([0, 5, 1, 1, 1, 2, 10]), 1.5, 2.5),
    (Pulse([0, 5, 1, 1, 1, 2, 10]), 3, 5), (Pulse([0, 5, 1, 1, 1, 2, 10]), 4.5, 2.5),
    (Pulse([0, 5, 1, 1, 1, 2, 10]), 11.5, 2.5), (Sine([1, 2, 1]), 0.25, 3),
    (PiecewiseLinear([0, 0, 2, 4]), 1, 2), (PiecewiseLinear([0, 0, 2, 4]), 5, 4),
])
def test_waveform_values(wave, t, expected):
    assert wave.value(t) == pytest.approx(expected)


def test_bad_waveforms():
    with pytest.raises(NetlistError, match="PWL needs pairs"):
        parse("V1 1 0 PWL(0 1 2)\nR1 1 0 1")
    with pytest.raises(NetlistError, match="SIN needs at least"):
        parse("V1 1 0 SIN(0 1)\nR1 1 0 1")


def test_bad_transient_settings():
    with pytest.raises(CircuitError):
        transient(parse(RC), -1)
    with pytest.raises(CircuitError):
        transient(parse(RC), 1e-3, method="rk4")
