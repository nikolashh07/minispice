"""Part D: sweeps, SPICE compatibility, speed, Monte Carlo, sensitivity, noise."""

import math
import os
import sys

import numpy as np
import pytest

from minispice import CircuitError, NetlistError, load, operating_point, parse
from minispice.analysis.montecarlo import monte_carlo, worst_case
from minispice.analysis.noise import noise_analysis
from minispice.analysis.sensitivity import sensitivity
from minispice.analysis.sweep import dc_sweep, parameter_sweep, step_values, sweep_values
from minispice.context import K_BOLTZMANN, kelvin, thermal_voltage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
DIVIDER_5 = "V1 1 0 10\nR1 1 2 1k tol=5%\nR2 2 0 1k tol=5%"


# ---- Phase 17: sweeps -----------------------------------------------------------------------------

def test_hand_check_diode_sweep_is_exponential():
    """Phase 17 hand check: sweeping a diode's voltage reproduces the Shockley curve from Phase 14."""
    result = dc_sweep(parse("V1 a 0 0\nD1 a 0"), "V1", sweep_values(0.3, 0.8, 0.05))
    current = result.measure("i(D1)")
    expected = 1e-14 * (np.exp(result.values / thermal_voltage(27)) - 1)
    assert current == pytest.approx(expected, rel=1e-6)
    # Exponential: every 60 mV (about Vt ln 10) multiplies the current by about 10.
    assert current[-1] / current[-2] == pytest.approx(math.exp(0.05 / thermal_voltage(27)), rel=1e-6)


def test_sweep_values():
    assert sweep_values(0, 1, 0.25).tolist() == [0, 0.25, 0.5, 0.75, 1.0]
    assert sweep_values(1, 0, 0.5).tolist() == [1.0, 0.5, 0.0]
    with pytest.raises(CircuitError):
        sweep_values(0, 1, 0)


def test_cmos_transfer_curve():
    result = dc_sweep(load(os.path.join(os.path.dirname(__file__), "..", "examples", "cmos_inverter.cir")), "VIN", sweep_values(0, 5, 0.1))
    vout = result.measure("v(out)")
    assert vout[0] == pytest.approx(5, abs=1e-3) and vout[-1] == pytest.approx(0, abs=1e-3)
    assert np.all(np.diff(vout) <= 1e-9)  # never rises as the input rises
    crossing = np.interp(2.5, vout[::-1], result.values[::-1])
    assert crossing == pytest.approx(2.5, abs=0.01)


def test_sweep_temperature_and_resistor():
    temps = dc_sweep(parse("I1 0 1 1m\nD1 1 0"), "temp", [0, 50, 100]).measure("v(1)")
    assert temps[0] > temps[1] > temps[2]
    r = dc_sweep(parse("V1 1 0 10\nR1 1 2 1k\nR2 2 0 1k"), "R2", [1e3, 3e3]).measure("v(2)")
    assert r.tolist() == pytest.approx([5, 7.5])


def test_parameter_sweep_reruns_any_analysis():
    results = parameter_sweep(parse("V1 1 0 10\nR1 1 2 1k\nR2 2 0 1k"), "R1", [1e3, 4e3], operating_point)
    assert [s.v(2) for _, s in results] == pytest.approx([5, 2])


def test_step_directive_values():
    assert step_values(["r1", "list", "1k", "2k"]) == ("r1", [1000, 2000])
    name, values = step_values(["r1", "1k", "3k", "1k"])
    assert values == pytest.approx([1000, 2000, 3000])


# ---- Phase 18: subcircuits and SPICE compatibility ------------------------------------------------

def test_hand_check_subcircuit_divider_matches_flat():
    """Phase 18 hand check: a subcircuit version of the divider gives the same answer as the flat one."""
    flat = operating_point(parse("V1 1 0 10\nR1 1 2 1k\nR2 2 0 1k"))
    sub = operating_point(parse(".subckt half in out\nRA in out 1k\nRB out 0 1k\n.ends\nV1 1 0 10\nX1 1 2 half"))
    assert sub.v(2) == pytest.approx(flat.v(2))
    assert sub.i("V1") == pytest.approx(flat.i("V1"))


def test_subcircuit_parameters_and_nesting():
    circuit = parse("""
.subckt res a b params: r=1k
R1 a b {r}
.ends
.subckt pair in out
X1 in mid res r=2k
X2 mid out res
.ends
V1 1 0 3
XP 1 2 pair
RL 2 0 1k
""")
    names = sorted(c.name for c in circuit.components)
    assert names == ["R1.XP.X1", "R1.XP.X2", "RL", "V1"]
    assert circuit.get("R1.XP.X1").value == 2000
    # 2k + 1k + 1k in series across 3 V: 0.75 mA, so V(2) = 0.75 V.
    assert operating_point(circuit).v(2) == pytest.approx(0.75)


def test_subcircuit_errors():
    with pytest.raises(NetlistError, match="has 2 ports"):
        parse(".subckt s a b\nR1 a b 1k\n.ends\nV1 1 0 1\nX1 1 s")
    with pytest.raises(NetlistError, match="isn't defined"):
        parse("V1 1 0 1\nX1 1 0 nothing")
    with pytest.raises(NetlistError, match="has no .ends"):
        parse(".subckt s a b\nR1 a b 1k\nV1 1 0 1")


def test_standard_spice_netlist():
    """A netlist written for another simulator: title line, $ comments, + continuations,
    .options/.print/.control lines, a model with parameters MiniSpice doesn't simulate."""
    circuit = load(os.path.join(os.path.dirname(__file__), "..", "examples", "spice_rc_filter.cir"))
    assert circuit.title.startswith("Second-order RC low-pass")
    assert any(".print" in w for w in circuit.warnings)
    from minispice.analysis.ac import ac_from_directive

    result = ac_from_directive(circuit, circuit.find_directives("ac")[0])
    assert abs(result.v("out")[0]) == pytest.approx(1, rel=1e-3)
    text = """Diode clipper from the internet
.MODEL D1N4148 D (IS=4.352E-9 N=1.906 BV=110 IBV=0.0001 RS=0.6458 CJO=7.048E-13 VJ=0.869 M=0.03 TT=3.48E-9)
V1 IN 0 DC 5V
R1 IN OUT 1K
D1 OUT 0 D1N4148
.OP
.END
"""
    circuit = parse(text)
    assert "CJO" in " ".join(circuit.warnings)
    assert 0.5 < operating_point(circuit).v("out") < 0.8


def test_four_terminal_spice_transistors():
    circuit = parse("VDD d 0 5\nVG g 0 3\nM1 d g 0 0 nmos\nVCC c 0 5\nRB c b 100k\nQ1 c b 0 0 npn")
    s = operating_point(circuit)
    assert s.i("M1") == pytest.approx(2e-3, rel=1e-6)
    assert s.region("Q1") == "active"


# ---- Phase 19: speed -----------------------------------------------------------------------------

def test_hand_check_sparse_matches_dense():
    """Phase 19 hand check: sparse and dense solvers give the same answer."""
    import benchmark

    circuit = parse(benchmark.mesh_netlist(400)[0])
    dense = operating_point(circuit, sparse=False).x
    sparse = operating_point(circuit, sparse=True).x
    assert np.allclose(dense, sparse, rtol=1e-12, atol=1e-14)


def test_big_circuit_is_fast():
    import time

    import benchmark

    circuit = parse(benchmark.mesh_netlist(10000)[0])
    start = time.perf_counter()
    solution = operating_point(circuit)
    assert time.perf_counter() - start < 5.0
    # Current in = current out: the source feeds exactly what leaves through the grounding resistor.
    assert -solution.i("V1") == pytest.approx(solution.i("RGND"), rel=1e-9)


# ---- Phase 20: tolerances and Monte Carlo ---------------------------------------------------------

def test_hand_check_monte_carlo_stays_in_hand_range():
    """Phase 20 hand check: with two 5 % resistors the middle voltage stays within 4.75 V to 5.25 V."""
    result = monte_carlo(parse(DIVIDER_5), "v(2)", runs=500)
    assert 4.75 <= result.low and result.high <= 5.25
    assert result.mean == pytest.approx(5, abs=0.02)
    assert result.fraction_within(4.75, 5.25) == 1.0


def test_worst_case_hits_hand_limits():
    result = worst_case(parse(DIVIDER_5), "v(2)")
    assert result.low == pytest.approx(4.75)
    assert result.high == pytest.approx(5.25)
    assert result.high_corner == pytest.approx({"R1": 950, "R2": 1050})


def test_monte_carlo_is_reproducible_and_gaussian_is_narrower():
    a = monte_carlo(parse(DIVIDER_5), "v(2)", runs=300, seed=7)
    b = monte_carlo(parse(DIVIDER_5), "v(2)", runs=300, seed=7)
    assert np.array_equal(a.values, b.values)
    g = monte_carlo(parse(DIVIDER_5), "v(2)", runs=300, seed=7, distribution="gaussian")
    assert g.std < a.std


def test_monte_carlo_needs_tolerances():
    with pytest.raises(CircuitError, match="tol=5%"):
        monte_carlo(parse("V1 1 0 1\nR1 1 0 1k"), "v(1)")


# ---- Phase 21: sensitivity ----------------------------------------------------------------------

def test_hand_check_divider_sensitivity():
    """Phase 21 hand check: in a divider both resistors have equal and opposite sensitivity."""
    ranked = {s.name: s for s in sensitivity(parse("V1 1 0 10\nR1 1 2 1k\nR2 2 0 1k"), "v(2)")}
    assert ranked["R1"].normalized == pytest.approx(-0.5, rel=1e-6)
    assert ranked["R2"].normalized == pytest.approx(0.5, rel=1e-6)
    # dV/dR2 = V R1/(R1+R2)² = 2.5 mV/Ω
    assert ranked["R2"].derivative == pytest.approx(10 * 1e3 / 2e3 ** 2, rel=1e-6)


def test_sensitivity_ranks_the_most_important_part_first():
    # Non-inverting amp gain 1 + RF/RG with a big RF and a small series resistor that barely matters.
    ranked = sensitivity(parse("VIN in 0 1\nRS in p 10\nU1 p m out\nRF out m 9k\nRG m 0 1k\nRL p 0 1meg"), "v(out)")
    names = [s.name for s in ranked]
    assert names[0] == "VIN"
    assert names.index("RF") < names.index("RS")
    assert ranked[-1].name in ("RS", "RL")


# ---- Phase 22: noise -----------------------------------------------------------------------------

def test_hand_check_resistor_noise():
    """Phase 22 hand check: a 1k resistor at room temperature has about 4 nV/√Hz of noise."""
    result = noise_analysis(parse("R1 out 0 1k"), "v(out)", f_start=10, f_stop=1e3, points=1)
    expected = math.sqrt(4 * K_BOLTZMANN * kelvin(27) * 1e3)
    assert result.output_density == pytest.approx(expected)
    assert expected == pytest.approx(4.07e-9, rel=1e-3)


def test_parallel_resistors_noise_like_their_equivalent():
    result = noise_analysis(parse("R1 out 0 2k\nR2 out 0 2k"), "v(out)", f_start=10, f_stop=100, points=1)
    assert result.output_density[0] == pytest.approx(math.sqrt(4 * K_BOLTZMANN * kelvin(27) * 1e3))
    assert dict(result.ranked_contributors()) == pytest.approx({"R1": 0.5, "R2": 0.5})


def test_kt_over_c():
    """Total noise of an RC filter is sqrt(kT/C), whatever R is."""
    for r in ("1k", "100k"):
        result = noise_analysis(parse(f"V1 in 0 0 AC 1\nR1 in out {r}\nC1 out 0 1n"), "v(out)", "V1", 0.01, 1e12, 40)
        assert result.total_rms() == pytest.approx(math.sqrt(K_BOLTZMANN * kelvin(27) / 1e-9), rel=0.01)


def test_input_referred_noise_of_amplifier():
    # Ideal non-inverting gain of 10: output noise / 10 is the input-referred noise.
    result = noise_analysis(parse("VIN in 0 0 AC 1\nRS in p 1k\nU1 p m out\nRF out m 9k\nRG m 0 1k"), "v(out)", "VIN", 100, 1000, 1)
    assert result.gain[0] == pytest.approx(10)
    assert result.input_density[0] == pytest.approx(result.output_density[0] / 10)


def test_diode_shot_noise():
    from minispice.context import Q_ELECTRON

    # 1 mA through a diode fed by an ideal current source: shot noise current sqrt(2qI) through rd = Vt/I.
    result = noise_analysis(parse("I1 0 a 1m\nD1 a 0"), "v(a)", f_start=10, f_stop=100, points=1)
    rd = thermal_voltage(27) / 1e-3
    assert result.output_density[0] == pytest.approx(math.sqrt(2 * Q_ELECTRON * 1e-3) * rd, rel=1e-3)
