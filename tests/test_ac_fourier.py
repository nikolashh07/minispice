import math

import numpy as np
import pytest

from minispice import CircuitError, NetlistError, operating_point, parse
from minispice.analysis.ac import ac_analysis, frequencies
from minispice.analysis.fourier import fourier, spectrum
from minispice.analysis.transient import transient

LOWPASS = "V1 1 0 DC 0 AC 1\nR1 1 2 1k\nC1 2 0 1u"
FC = 1 / (2 * math.pi * 1e3 * 1e-6)


# ---- Phase 9: AC ----------------------------------------------------------------------------------

def test_hand_check_lowpass_corner():
    """Phase 9 hand check: at f = 1/(2πRC) the output is down 3 dB with a phase of -45°."""
    r = ac_analysis(parse(LOWPASS), FC, FC * 2, 2, "lin")
    assert r.measure("vdb(2)")[0] == pytest.approx(-3.0103, abs=1e-3)
    assert r.measure("vp(2)")[0] == pytest.approx(-45, abs=1e-6)


def test_corner_frequency_found_from_sweep():
    r = ac_analysis(parse(LOWPASS), 1, 100e3, 50)
    assert r.corner_frequency("v(2)") == pytest.approx(FC, rel=1e-3)


def test_lowpass_rolls_off_20db_per_decade():
    r = ac_analysis(parse(LOWPASS), 10e3, 100e3, 1)
    mags = r.measure("vdb(2)")
    assert mags[0] - mags[-1] == pytest.approx(20, abs=0.1)


def test_impedances_match_formulas():
    # A 1 A AC current into each part gives V = Z.
    f = 1000.0
    w = 2 * math.pi * f
    r = ac_analysis(parse("I1 0 1 AC 1\nR1 1 0 50\nI2 0 2 AC 1\nC1 2 0 1u\nR9 2 0 1g\nI3 0 3 AC 1\nL1 3 0 1m"), f, 2 * f, 2, "lin")
    assert r.v(1)[0] == pytest.approx(50)
    zc = 1 / (1j * w * 1e-6)
    assert r.v(2)[0] == pytest.approx(zc * 1e9 / (zc + 1e9), rel=1e-6)
    assert r.v(3)[0] == pytest.approx(1j * w * 1e-3)


def test_series_rlc_resonance():
    r = ac_analysis(parse("V1 1 0 AC 1\nL1 1 2 1m\nC1 2 3 1u\nR1 3 0 10"), 1e3, 20e3, 400)
    current = np.abs(r.i("R1"))
    f_peak = r.freqs[np.argmax(current)]
    assert f_peak == pytest.approx(1 / (2 * math.pi * math.sqrt(1e-9)), rel=0.01)
    assert current.max() == pytest.approx(0.1, rel=1e-3)  # at resonance only R limits the current


def test_frequency_grids():
    assert len(frequencies("dec", 10, 1, 1000)) == 31
    assert frequencies("lin", 5, 1, 5).tolist() == [1, 2, 3, 4, 5]
    with pytest.raises(CircuitError):
        frequencies("dec", 10, 100, 1)


def test_ac_needs_an_ac_source():
    with pytest.raises(CircuitError, match="needs a source with an AC value"):
        ac_analysis(parse("V1 1 0 5\nR1 1 0 1k"), 1, 10)


def test_ac_phase_input():
    r = ac_analysis(parse("V1 1 0 AC 2 90\nR1 1 0 1k"), 10, 20, 2, "lin")
    assert r.v(1)[0] == pytest.approx(2j)


# ---- Phase 10: Fourier --------------------------------------------------------------------------

def test_hand_check_square_wave_harmonics():
    """Phase 10 hand check: a square wave has only odd harmonics, sized 1, 1/3, 1/5, ..."""
    r = transient(parse("V1 1 0 PULSE(-1 1 0 1n 1n 0.5m 1m)\nR1 1 0 1k"), 5e-3, 1e-5)
    f = fourier(r.times, r.v(1), 1e3, 9)
    rel = f.normalized()
    for n in (3, 5, 7, 9):
        assert rel[n - 1] == pytest.approx(1 / n, rel=0.01)
    for n in (2, 4, 6, 8):
        assert rel[n - 1] == pytest.approx(0, abs=1e-3)
    # Fourier series: the fundamental of a ±1 square wave is 4/π.
    assert f.magnitudes[0] == pytest.approx(4 / math.pi, rel=0.01)


def test_pure_sine_has_no_distortion():
    t = np.linspace(0, 3e-3, 3001)
    f = fourier(t, 2 * np.sin(2 * np.pi * 1e3 * t) + 0.5, 1e3)
    assert f.magnitudes[0] == pytest.approx(2, rel=1e-4)
    assert f.dc == pytest.approx(0.5, abs=1e-4)
    assert f.thd < 1e-3


def test_thd_of_known_mix():
    t = np.linspace(0, 1e-3, 4001)
    v = np.sin(2 * np.pi * 1e3 * t) + 0.1 * np.sin(2 * np.pi * 3e3 * t)
    assert fourier(t, v, 1e3).thd == pytest.approx(0.1, rel=1e-3)


def test_fourier_needs_a_full_period():
    with pytest.raises(CircuitError, match="needs at least 1 full period"):
        fourier([0, 1e-4], [0, 1], 1e3)


def test_spectrum_finds_the_tone():
    t = np.linspace(0, 10e-3, 10001)
    freqs, amps = spectrum(t, 3 * np.sin(2 * np.pi * 2e3 * t))
    assert freqs[np.argmax(amps[1:]) + 1] == pytest.approx(2e3, rel=0.02)


# ---- Phase 11: transformers and switches --------------------------------------------------------

def test_hand_check_transformer():
    """Phase 11 hand check: a 10:1 transformer steps 120 V down to 12 V; currents scale the other way."""
    s = operating_point(parse("V1 1 0 120\nT1 1 0 2 0 10\nRL 2 0 12"))
    assert s.v(2) == pytest.approx(12)
    assert s.i("RL") == pytest.approx(1.0)
    assert -s.i("V1") == pytest.approx(0.1)
    # Ideal: power in = power out.
    assert s.p("T1") == pytest.approx(0, abs=1e-12)


def test_coupled_inductors_act_as_transformer_in_ac():
    # Perfect coupling, L1/L2 = 100 → turns ratio √100 = 10. Large inductances so jωL dominates the load.
    r = ac_analysis(parse("V1 1 0 AC 120\nL1 1 0 100\nL2 2 0 1\nK1 L1 L2 1\nRL 2 0 1meg"), 1e3, 2e3, 2, "lin")
    assert abs(r.v(2)[0]) == pytest.approx(12, rel=1e-3)


def test_coupled_inductors_in_transient():
    # A source straight across an inductor is a short at DC, so give the source 1 Ω of resistance.
    r = transient(parse("V1 3 0 SIN(0 10 1k)\nRs 3 1 1\nL1 1 0 100\nL2 2 0 1\nK1 L1 L2 0.999\nRL 2 0 1meg"), 2e-3, 1e-6)
    peak = np.max(np.abs(r.v(2)[r.times > 1e-3]))
    assert peak == pytest.approx(0.999, rel=0.01)


def test_mutual_inductance_value():
    circuit = parse("L1 1 0 4m\nL2 2 0 1m\nK1 L1 L2 0.5\nV1 1 0 1\nR1 2 0 1")
    from minispice.mna import Layout

    Layout(circuit)
    assert circuit.get("K1").mutual == pytest.approx(0.5 * math.sqrt(4e-3 * 1e-3))


def test_bad_coupling():
    with pytest.raises(NetlistError, match="no part with that name"):
        parse("L1 1 0 1m\nK1 L1 L9 0.5\nV1 1 0 1")
    with pytest.raises(NetlistError, match="between 0 and 1"):
        parse("L1 1 0 1m\nL2 2 0 1m\nK1 L1 L2 1.5\nV1 1 0 1")


def test_switch_opens_and_closes():
    r = transient(parse("V1 1 0 5\nS1 1 2 ton=1m toff=2m\nR1 2 0 1k"), 3e-3, 1e-5)
    assert r.at("v(2)", 0.5e-3) == pytest.approx(0, abs=1e-3)
    assert r.at("v(2)", 1.5e-3) == pytest.approx(5, rel=1e-3)
    assert r.at("v(2)", 2.5e-3) == pytest.approx(0, abs=1e-3)
    assert any(abs(t - 1e-3) < 1e-12 for t in r.times)  # landed exactly on the switching time


def test_spice_style_switch_is_explained():
    with pytest.raises(NetlistError, match="controlled by time"):
        parse("S1 1 2 3 4 swmod\nV1 1 0 1\nR1 2 0 1")
