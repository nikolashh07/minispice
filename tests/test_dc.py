import numpy as np
import pytest

from minispice import CircuitError, operating_point, parse
from minispice.explain import Recorder


def solve(text):
    return operating_point(parse(text))


def test_hand_check_current_into_resistor():
    """Phase 2 hand check: 1 mA into a 2k resistor to ground gives V = I R = 2 V."""
    s = solve("I1 0 1 1m\nR1 1 0 2k")
    assert s.v(1) == pytest.approx(2.0)


def test_stamp_matrix_for_hand_check():
    """The nodal matrix for the Phase 2 circuit is the 1x1 equation (1/2k) V1 = 1 mA."""
    rec = Recorder()
    operating_point(parse("I1 0 1 1m\nR1 1 0 2k"), recorder=rec)
    assert rec.matrix == pytest.approx(np.array([[0.5e-3]]))
    assert rec.rhs == pytest.approx(np.array([1e-3]))


def test_two_node_resistor_network():
    # 1 mA into node 1; R1 1-2 1k, R2 2-0 1k, R3 1-0 2k. By hand: R1+R2 = 2k parallel with R3 = 1k, V1 = 1 V.
    s = solve("I1 0 1 1m\nR1 1 2 1k\nR2 2 0 1k\nR3 1 0 2k")
    assert s.v(1) == pytest.approx(1.0)
    assert s.v(2) == pytest.approx(0.5)


def test_hand_check_divider():
    """Phase 3 hand check: 10 V across two 1k resistors gives 5 V and 5 mA."""
    s = solve("V1 1 0 DC 10\nR1 1 2 1k\nR2 2 0 1k")
    assert s.v(2) == pytest.approx(5.0)
    assert s.i("R1") == pytest.approx(5e-3)
    # Passive sign convention: the source delivers power, so its current is negative.
    assert s.i("V1") == pytest.approx(-5e-3)


def test_expanded_matrix_for_divider():
    """Unknowns V1, V2, I(V1). The source adds the third row V1 = 10 and the third column."""
    rec = Recorder()
    operating_point(parse("V1 1 0 DC 10\nR1 1 2 1k\nR2 2 0 1k"), recorder=rec)
    g = 1e-3
    expected = np.array([[g, -g, 1], [-g, 2 * g, 0], [1, 0, 0]])
    assert rec.unknowns == ["V(1)", "V(2)", "I(V1)"]
    assert rec.matrix == pytest.approx(expected)
    assert rec.rhs == pytest.approx([0, 0, 10])


def test_hand_check_two_sources():
    """Phase 3 textbook-style check: KCL at node 2 gives 7 V = 40, so V = 40/7."""
    s = solve("V1 1 0 10\nR1 1 2 2k\nR2 2 0 4k\nR3 2 3 1k\nV2 3 0 5")
    assert s.v(2) == pytest.approx(40 / 7)
    assert s.i("V2") == pytest.approx((40 / 7 - 5) / 1e3)


def test_floating_voltage_source_between_nodes():
    s = solve("V1 1 0 10\nV2 2 1 5\nR1 2 0 1k")
    assert s.v(2) == pytest.approx(15)


def test_kcl_holds_at_every_node():
    s = solve("V1 1 0 10\nR1 1 2 2k\nR2 2 0 4k\nR3 2 3 1k\nV2 3 0 5\nI1 2 0 1m")
    for node in ["1", "2", "3"]:
        total = 0.0
        for comp in s.circuit.components:
            for n, current in zip(comp.nodes, comp.terminal_currents(s.x, s.ctx)):
                if n == node:
                    total += current
        assert total == pytest.approx(0, abs=1e-12)


def test_floating_node_is_explained():
    with pytest.raises(CircuitError, match=r"Node\(s\) 3, 4 have no DC path to ground"):
        solve("V1 1 0 10\nR1 1 0 1k\nR2 3 4 1k\nR3 4 3 1k")


def test_voltage_source_loop_is_explained():
    with pytest.raises(CircuitError, match="V1, V2 form a loop"):
        solve("V1 1 0 10\nV2 1 0 5\nR1 1 0 1k")


def test_no_ground_is_explained():
    with pytest.raises(CircuitError, match="Nothing is connected to ground"):
        solve("V1 1 2 10\nR1 1 2 1k")


def test_node_only_on_current_source_is_explained():
    with pytest.raises(CircuitError, match="no DC path"):
        solve("I1 0 1 1m\nI2 1 0 2m")


def test_unknown_node_and_part_names():
    s = solve("V1 1 0 10\nR1 1 0 1k")
    with pytest.raises(CircuitError, match="no node 'x'"):
        s.v("x")
    with pytest.raises(CircuitError, match="no component named 'R7'"):
        s.i("R7")


def test_probe_expressions():
    s = solve("V1 1 0 DC 10\nR1 1 2 1k\nR2 2 0 1k")
    assert s["v(2)"] == pytest.approx(5)
    assert s["v(1,2)"] == pytest.approx(5)
    assert s["i(R1)"] == pytest.approx(5e-3)
    assert s["p(R1)"] == pytest.approx(25e-3)


def test_explain_notes_name_the_laws():
    rec = Recorder()
    operating_point(parse("V1 1 0 DC 10\nR1 1 2 1k\nR2 2 0 1k"), recorder=rec)
    laws = {note.law for note in rec.notes}
    assert {"Ohm's law", "KVL"} <= laws
    assert any("R1" in note.parts for note in rec.notes)


def test_dense_and_sparse_agree():
    circuit = parse("V1 1 0 10\nR1 1 2 2k\nR2 2 0 4k\nR3 2 3 1k\nV2 3 0 5")
    dense = operating_point(circuit, sparse=False).x
    sparse = operating_point(circuit, sparse=True).x
    assert np.allclose(dense, sparse, rtol=1e-12, atol=1e-15)
