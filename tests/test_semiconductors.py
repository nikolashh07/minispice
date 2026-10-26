"""Part C, Phases 14-16: diodes, Newton's method, transistors, temperature."""

import math

import pytest

from minispice import NetlistError, operating_point, parse
from minispice.analysis.ac import ac_analysis
from minispice.components.junction import pnjlim
from minispice.context import thermal_voltage
from minispice.explain import Recorder


def op(text, temperature=None):
    circuit = parse(text)
    if temperature is not None:
        circuit.temperature = temperature
    return operating_point(circuit)


# ---- Phase 14: diodes and Newton's method -------------------------------------------------------

def test_hand_check_diode():
    """Phase 14 hand check: 5 V, 1k and a diode give about 0.6-0.7 V and about 4.3 mA."""
    s = op("V1 1 0 5\nR1 1 2 1k\nD1 2 0")
    assert 0.6 < s.v(2) < 0.7
    assert s.i("R1") == pytest.approx(4.3e-3, rel=0.01)
    # The answer satisfies both the resistor and the Shockley equation at once.
    vt = thermal_voltage(27)
    assert s.i("R1") == pytest.approx(1e-14 * (math.exp(s.v(2) / vt) - 1), rel=1e-6)


def test_one_newton_iteration_by_hand():
    """The first Newton step from a 0.7 V guess, done by hand, matches what the solver computes.

    At 0.7 V the diode carries Id = IS e^(0.7/Vt) and has conductance g = Id/Vt. Its tangent line
    is g in parallel with a current source Ieq = Id - g·0.7. KCL at node 2:
        (V - 5)/1k + g V + Ieq = 0   ->   V = (5/1k - Ieq) / (1/1k + g)
    """
    from minispice.components.diode import Diode

    vt = thermal_voltage(27)
    id0 = 1e-14 * (math.exp(0.7 / vt) - 1)
    g = 1e-14 * math.exp(0.7 / vt) / vt
    ieq = id0 - g * 0.7
    v_hand = (5 / 1e3 - ieq) / (1 / 1e3 + g)

    diode = parse("D1 2 0\nV1 1 0 5\nR1 1 2 1k").get("D1")
    assert isinstance(diode, Diode)
    i, g_code = diode.junction(0.7, 27, 0.0)
    assert i == pytest.approx(id0)
    assert g_code == pytest.approx(g)
    # The next guess gets closer to the answer from the other side.
    assert 0.69 < v_hand < 0.7


def test_newton_converges_quickly():
    s = op("V1 1 0 5\nR1 1 2 1k\nD1 2 0")
    assert s.iterations < 30


def test_voltage_limiting_prevents_overflow():
    # 1000 V into 1 Ω: without limiting the first Newton step would ask for e^(1000/0.026).
    s = op("V1 1 0 1000\nR1 1 2 1\nD1 2 0")
    assert s.i("R1") == pytest.approx(999, rel=1e-3)
    assert s.v(2) < 1.2


def test_pnjlim_follows_the_curve():
    v, limited = pnjlim(5.0, 0.6, 0.02585, 0.6)
    assert limited and 0.6 < v < 0.8
    v, limited = pnjlim(0.61, 0.6, 0.02585, 0.6)
    assert not limited and v == 0.61


def test_reverse_biased_diode_blocks():
    s = op("V1 1 0 5\nR1 1 2 1k\nD1 0 2")
    assert s.v(2) == pytest.approx(5, rel=1e-6)
    assert s.region("D1") == "off"


def test_zener_regulates():
    loads = [op(f"V1 in 0 {vin}\nR1 in out 1k\nD1 0 out zener5v1\nRL out 0 10k").v("out") for vin in (8, 10, 12)]
    assert all(5.05 < v < 5.25 for v in loads)
    assert max(loads) - min(loads) < 0.1  # the input changes by 4 V, the output by under 0.1 V


def test_led_turns_on_near_two_volts():
    s = op("V1 1 0 5\nR1 1 a 330\nD1 a 0 led_red")
    assert 1.7 < s.v("a") < 1.9
    assert s.region("D1") == "on"


def test_diode_series_resistance():
    s = op("I1 0 a 100m\nD1 a 0 1n4148")
    plain = op("I1 0 a 100m\nD1 a 0 mydiode\n.model mydiode D(IS=2.52n N=1.752)")
    assert s.v("a") - plain.v("a") == pytest.approx(0.1 * 0.568, rel=1e-3)


def test_diode_small_signal_resistance():
    # At 1 mA a diode looks like rd = Vt / I ≈ 26 Ω to small signals.
    r = ac_analysis(parse("I1 0 a DC 1m AC 1u\nD1 a 0"), 1e3, 2e3, 2, "lin")
    assert abs(r.v("a")[0]) / 1e-6 == pytest.approx(thermal_voltage(27) / 1e-3, rel=1e-3)


def test_unknown_model_is_explained():
    with pytest.raises(NetlistError, match="isn't defined. Add a .model line"):
        parse("D1 1 0 nosuch\nV1 1 0 1")
    with pytest.raises(NetlistError, match="needs a D model"):
        parse("D1 1 0 2n3904\nV1 1 0 1")


# ---- Phase 15: transistors -----------------------------------------------------------------------

BJT_BIAS = """VCC vcc 0 22
R1 vcc b 39k
R2 b 0 3.9k
RC vcc c 10k
RE e 0 1.5k
Q1 c b e mynpn
.model mynpn NPN(BF=140 IS=1e-14)"""


def test_hand_check_bjt_bias():
    """Phase 15 hand check: textbook approximate analysis gives VB = 2 V, IC = 0.867 mA, VCE = 12 V."""
    s = op(BJT_BIAS)
    assert s.v("b") == pytest.approx(2.0, rel=0.03)
    assert s.i("Q1") == pytest.approx(0.867e-3, rel=0.03)
    assert s.v("c", "e") == pytest.approx(12.0, rel=0.03)
    assert s.region("Q1") == "active"


def test_bjt_currents_obey_beta_and_kcl():
    s = op(BJT_BIAS)
    ic, ib, ie = (s.i("Q1", t) for t in ("c", "b", "e"))
    assert ic / ib == pytest.approx(140, rel=1e-3)
    assert ic + ib + ie == pytest.approx(0, abs=1e-15)


def test_bjt_regions():
    assert op("VCC vcc 0 5\nRB vcc b 1meg\nRC vcc c 1k\nQ1 c b 0 npn").region("Q1") == "active"
    sat = op("VCC vcc 0 5\nRB vcc b 10k\nRC vcc c 1k\nQ1 c b 0 npn")
    assert sat.region("Q1") == "saturation"
    assert sat.v("c") < 0.2
    assert op("VCC vcc 0 5\nRB 0 b 10k\nRC vcc c 1k\nQ1 c b 0 npn").region("Q1") == "cutoff"


def test_pnp_mirrors_npn():
    npn = op("VCC vcc 0 10\nRB vcc b 1meg\nRC vcc c 1k\nQ1 c b 0 npn")
    pnp = op("VCC vcc 0 -10\nRB vcc b 1meg\nRC vcc c 1k\nQ1 c b 0 pnp")
    assert pnp.v("c") == pytest.approx(-npn.v("c"), rel=1e-9)
    assert pnp.i("Q1") == pytest.approx(-npn.i("Q1"), rel=1e-9)


def test_hand_check_mosfet_saturation():
    """Phase 15 hand check: Id = ½ k (Vgs - Vt)² in saturation."""
    for vgs in (2.0, 3.0, 4.0):
        s = op(f"VDD d 0 10\nVG g 0 {vgs}\nM1 d g 0 nmos")
        assert s.i("M1") == pytest.approx(0.5 * 1e-3 * (vgs - 1) ** 2, rel=1e-6)
        assert s.region("M1") == "saturation"


def test_mosfet_linear_and_cutoff():
    s = op("VDD d 0 0.5\nVG g 0 3\nM1 d g 0 nmos")
    assert s.i("M1") == pytest.approx(1e-3 * ((3 - 1) * 0.5 - 0.5 ** 2 / 2), rel=1e-6)
    assert s.region("M1") == "linear"
    assert op("VDD d 0 5\nVG g 0 0.5\nM1 d g 0 nmos").region("M1") == "cutoff"


def test_mosfet_width_and_length():
    s = op("VDD d 0 5\nVG g 0 2\nM1 d g 0 nmos w=10u l=1u")
    assert s.i("M1") == pytest.approx(0.5 * 1e-3 * 10 * 1 ** 2, rel=1e-6)


def test_pmos_mirrors_nmos():
    s = op("VSS s 0 5\nVG g 0 2\nM1 d g s pmos\nRD d 0 100")
    assert s.i("RD") == pytest.approx(0.5e-3 * (3 - 1) ** 2, rel=1e-3)


def test_hand_check_cmos_inverter():
    """Phase 15 hand check: the inverter output flips when the input crosses the middle."""
    def vout(vin):
        return op(f"VDD vdd 0 5\nVIN in 0 {vin}\nM1 out in 0 nmos\nM2 out in vdd pmos").v("out")

    # Newton's method stops once a step changes the answer by under 0.1 % + 1 µV.
    assert vout(0) == pytest.approx(5, abs=1e-4)
    assert vout(5) == pytest.approx(0, abs=1e-4)
    assert vout(2.5) == pytest.approx(2.5, abs=1e-4)
    assert vout(2.3) > 4 and vout(2.7) < 1


def test_mosfet_gate_alone_floats():
    with pytest.raises(Exception, match="no DC path"):
        op("VDD d 0 5\nM1 d g 0 nmos")


# ---- Phase 16: temperature ----------------------------------------------------------------------

def test_hand_check_diode_tempco():
    """Phase 16 hand check: a silicon diode's voltage drops roughly 2 mV per °C of heating."""
    cold = op("I1 0 1 1m\nD1 1 0", temperature=27).v(1)
    hot = op("I1 0 1 1m\nD1 1 0", temperature=77).v(1)
    per_degree = (hot - cold) / 50
    assert -2.5e-3 < per_degree < -1.5e-3


def test_thermal_voltage():
    assert thermal_voltage(27) == pytest.approx(0.025865, rel=1e-4)


def test_resistor_temperature_coefficient():
    # Copper-like tc1 = 0.0039 /°C: 100 °C hotter means 39 % more resistance.
    s = op("I1 0 1 1m\nR1 1 0 1k tc1=0.0039", temperature=127)
    assert s.v(1) == pytest.approx(1.39)


def test_temp_directive():
    assert parse("I1 0 1 1m\nD1 1 0\n.temp 100").temperature == 100


def test_power_balances_in_nonlinear_circuits():
    from minispice.power import power_report

    assert power_report(op(BJT_BIAS)).balanced
    assert power_report(op("VDD vdd 0 5\nVIN in 0 2.4\nM1 out in 0 nmos\nM2 out in vdd pmos")).balanced
