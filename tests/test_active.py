"""Part C, Phases 12-13: controlled sources and op-amps."""

import math

import numpy as np
import pytest

from minispice import CircuitError, NetlistError, operating_point, parse
from minispice.analysis.ac import ac_analysis
from minispice.analysis.transient import transient
from minispice.power import power_report
from minispice.theorems import thevenin


def op(text):
    return operating_point(parse(text))


# ---- Phase 12: controlled sources ---------------------------------------------------------------

def test_hand_check_vccs():
    """Phase 12 hand check: gm = 0.01 S with 1 V of control into 1k gives 10 V across the load."""
    s = op("V1 c 0 1\nG1 0 out c 0 0.01\nRL out 0 1k")
    assert s.v("out") == pytest.approx(10)


def test_vcvs():
    s = op("V1 c 0 2\nE1 out 0 c 0 3\nRL out 0 1k")
    assert s.v("out") == pytest.approx(6)


def test_cccs_models_beta():
    # A crude BJT: 10 µA base current times beta = 100 gives 1 mA through the 1k collector resistor.
    s = op("IB 0 b 10u\nVSENSE b 0 0\nF1 c 0 VSENSE 100\nRC vcc c 1k\nVCC vcc 0 5")
    assert s.i("RC") == pytest.approx(1e-3)
    assert s.v("c") == pytest.approx(4)


def test_ccvs():
    s = op("I1 0 1 2m\nVS 1 0 0\nH1 out 0 VS 500\nRL out 0 1k")
    # The sensed current flows into VS's + terminal: I(VS) = 2 mA, so V(out) = 500 × 2 mA = 1 V.
    assert s.v("out") == pytest.approx(1.0)


def test_current_control_must_be_a_branch_part():
    with pytest.raises(NetlistError, match="Add a 0 V source in series"):
        parse("V1 1 0 1\nR1 1 0 1k\nF1 2 0 R1 10\nR2 2 0 1k")
    with pytest.raises(NetlistError, match="no part with that name"):
        parse("V1 1 0 1\nF1 2 0 VX 10\nR2 2 0 1k")


def test_controlled_sources_conserve_power():
    s = op("V1 c 0 1\nR9 c 0 1k\nG1 0 out c 0 0.01\nRL out 0 1k\nE1 o2 0 out 0 2\nR2 o2 0 2k")
    assert power_report(s).balanced


def test_thevenin_with_dependent_source():
    # Combining resistors can't give Rth with a dependent source; the 1 A test-source method can.
    # E1 makes V(2) = 2 V(1), so the open-circuit voltage at 3 is 2 V and Rth is just R2.
    circuit = parse("V1 1 0 1\nE1 2 0 1 0 2\nR2 2 3 1k\nR3 3 0 1meg")
    th = thevenin(circuit, "3", remove=["R3"])
    assert th.vth == pytest.approx(2.0)
    assert th.rth == pytest.approx(1000)


def test_thevenin_with_feedback_dependent_source():
    # VCCS feedback: G1 pushes 1 mS × V(a) out of node a, which halves the resistance seen there.
    th = thevenin(parse("R1 a 0 1k\nG1 a 0 a 0 1m\nI9 0 a 0"), "a")
    assert th.rth == pytest.approx(500)


# ---- Phase 13: op-amps -------------------------------------------------------------------------

def test_hand_check_inverting_amplifier():
    """Phase 13 hand check: gain = -Rf/Rin."""
    for rf, rin in ((10e3, 1e3), (47e3, 4.7e3), (5e3, 10e3)):
        s = op(f"VIN in 0 0.2\nRIN in m {rin}\nRF m out {rf}\nU1 0 m out")
        assert s.v("out") / 0.2 == pytest.approx(-rf / rin)
        assert s.v("m") == pytest.approx(0, abs=1e-12)  # virtual ground


def test_hand_check_noninverting_amplifier():
    """Phase 13 hand check: gain = 1 + Rf/Rg."""
    s = op("VIN in 0 0.3\nU1 in m out\nRF out m 9k\nRG m 0 1k")
    assert s.v("out") / 0.3 == pytest.approx(10)


def test_hand_check_output_clips_at_rails():
    """Phase 13 hand check: the output can't go past the supply rails."""
    s = op("VIN in 0 2\nRIN in m 1k\nRF m out 100k\nU1 0 m out a=100k vpos=15 vneg=-15")
    assert s.v("out") == pytest.approx(-15, abs=0.01)
    s = op("VIN in 0 -2\nRIN in m 1k\nRF m out 100k\nU1 0 m out a=100k vpos=12 vneg=0")
    assert s.v("out") == pytest.approx(12, abs=0.01)


def test_realistic_opamp_in_linear_region_matches_ideal():
    s = op("VIN in 0 0.1\nRIN in m 1k\nRF m out 10k\nU1 0 m out a=200k vpos=15 vneg=-15")
    # Finite gain A: closed-loop gain = -(Rf/Rin) / (1 + (1 + Rf/Rin)/A)
    assert s.v("out") == pytest.approx(-1.0 / (1 + 11 / 200e3), rel=1e-6)


def test_ideal_opamp_without_feedback_is_explained():
    with pytest.raises(CircuitError):
        op("VIN in 0 1\nU1 in 0 out\nRL out 0 1k")


def test_gain_bandwidth_sets_closed_loop_bandwidth():
    # Non-inverting gain 10 with GBW = 1 MHz: bandwidth ≈ 1 MHz / 10 = 100 kHz.
    r = ac_analysis(parse("VIN in 0 AC 1\nU1 in m out a=100k gbw=1meg\nRF out m 9k\nRG m 0 1k"), 1e3, 10e6, 50)
    assert abs(r.v("out")[0]) == pytest.approx(10, rel=1e-3)
    assert r.corner_frequency("v(out)") == pytest.approx(100e3, rel=0.02)


def test_open_loop_pole():
    r = ac_analysis(parse("VIN in 0 AC 1u\nU1 in 0 out a=100k gbw=1meg\nRL out 0 1k"), 1, 1e6, 20)
    # One pole at GBW/A = 10 Hz.
    assert r.corner_frequency("v(out)") == pytest.approx(10, rel=0.02)


def test_opamp_bandwidth_in_transient():
    # Unity-gain follower with GBW = 1 MHz responds to a step with τ = 1/(2π · 1 MHz).
    r = transient(parse("VIN in 0 STEP(0 1 0)\nU1 in out out a=100k gbw=1meg\nRL out 0 10k"), 1e-6, 1e-8)
    tau = 1 / (2 * math.pi * 1e6)
    assert r.at("v(out)", tau) == pytest.approx(1 - math.exp(-1), rel=0.02)


def test_opamp_model_from_library():
    s = op("VIN in 0 1\nRIN in m 1k\nRF m out 100k\nU1 0 m out lm741")
    assert s.v("out") == pytest.approx(-15, abs=0.01)


def test_opamp_ac_ideal():
    r = ac_analysis(parse("VIN in 0 AC 1\nRIN in m 1k\nRF m out 4k\nU1 0 m out"), 100, 1000, 2)
    assert np.allclose(r.v("out"), -4)
