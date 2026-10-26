import pytest

from minispice import CircuitError, operating_point, parse
from minispice.power import power_report
from minispice.theorems import max_power_transfer, norton, superposition, thevenin

DIVIDER = "V1 1 0 DC 10\nR1 1 2 1k\nR2 2 0 1k"
THEVENIN = "V1 1 0 12\nR1 1 2 6k\nR2 2 0 3k\nR3 2 3 2k\nRL 3 0 4k"


# ---- Phase 4: power -----------------------------------------------------------------------------

def test_hand_check_divider_power():
    """Phase 4 hand check: each resistor absorbs 25 mW and the source delivers 50 mW."""
    s = operating_point(parse(DIVIDER))
    assert s.p("R1") == pytest.approx(25e-3)
    assert s.p("R2") == pytest.approx(25e-3)
    assert s.p("V1") == pytest.approx(-50e-3)
    report = power_report(s)
    assert report.delivered == pytest.approx(50e-3)
    assert report.absorbed == pytest.approx(50e-3)
    assert report.balanced


def test_power_balances_with_several_sources():
    s = operating_point(parse("V1 1 0 10\nR1 1 2 2k\nR2 2 0 4k\nR3 2 3 1k\nV2 3 0 5\nI1 0 3 2m"))
    report = power_report(s)
    assert report.imbalance == pytest.approx(0, abs=1e-15)
    # V2 is being charged by the rest of the circuit, so it absorbs power.
    assert s.p("V2") > 0


def test_overheating_warning():
    # 10 V across 100 Ω is 1 W, far more than a 1/4 W resistor can take.
    s = operating_point(parse("V1 1 0 10\nR1 1 0 100 rating=0.25"))
    report = power_report(s)
    assert report.rows[1].overheating
    assert "R1 absorbs 1 W but is rated for 250 mW" in report.warnings[0]
    assert "rated 1 W or more" in report.warnings[0]


# ---- Phase 5: theorems --------------------------------------------------------------------------

def test_hand_check_thevenin():
    """Phase 5 hand check: Vth = 12·3k/9k = 4 V, Rth = 6k||3k + 2k = 4k."""
    th = thevenin(parse(THEVENIN), "3", remove=["RL"])
    assert th.vth == pytest.approx(4.0)
    assert th.rth == pytest.approx(4000)


def test_norton_matches_thevenin():
    i_n, r_n = norton(parse(THEVENIN), "3", remove=["RL"])
    assert i_n == pytest.approx(1e-3)
    assert r_n == pytest.approx(4000)


def test_max_power_transfer():
    rl, pmax, _ = max_power_transfer(parse(THEVENIN), "3", remove=["RL"])
    assert rl == pytest.approx(4000)
    assert pmax == pytest.approx(1e-3)
    # The real circuit with RL = 4k does deliver exactly that.
    assert operating_point(parse(THEVENIN)).p("RL") == pytest.approx(pmax)
    # And any other load gets less.
    for other in (2000, 3000, 5000, 8000):
        circuit = parse(THEVENIN)
        circuit.get("RL").value = other
        assert operating_point(circuit).p("RL") < pmax


def test_superposition_parts_add_up():
    result = superposition(parse("V1 1 0 10\nR1 1 2 2k\nR2 2 0 4k\nR3 2 3 1k\nV2 3 0 5\nI1 0 2 1m"))
    total, parts = result.node_breakdown()["2"]
    assert set(parts) == {"V1", "V2", "I1"}
    assert sum(parts.values()) == pytest.approx(total)
    assert result.max_error() < 1e-12
    # V1 alone: 10 V into 2k with (4k || 1k = 800) to ground.
    assert parts["V1"] == pytest.approx(10 * 800 / 2800)


def test_ideal_source_has_no_norton():
    with pytest.raises(CircuitError, match="no Norton equivalent"):
        norton(parse("V1 1 0 5\nR1 1 0 1k"), "1")


def test_bad_theorem_nodes():
    with pytest.raises(CircuitError, match="isn't connected"):
        thevenin(parse(DIVIDER), "9")
