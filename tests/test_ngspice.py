"""Phase 23: MiniSpice agrees with ngspice. Skipped when ngspice isn't installed."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import compare_ngspice  # noqa: E402

from minispice import parse  # noqa: E402


def test_netlist_for_ngspice_writes_out_builtin_models():
    circuit = parse("V1 1 0 5\nR1 1 2 1k\nD1 2 0 1n4148\nM1 2 3 0 nmos\nV3 3 0 2")
    text = compare_ngspice.ngspice_netlist(circuit)
    assert ".model 1n4148 D(IS=2.52e-09" in text
    assert ".model nmos NMOS(VTO=1 KP=0.001 LEVEL=1)" in text
    assert text.rstrip().endswith(".end")


def test_minispice_only_parts_are_skipped():
    assert not compare_ngspice.compatible(parse("V1 1 0 1\nT1 1 0 2 0 10\nR1 2 0 1"))
    assert not compare_ngspice.compatible(parse("V1 1 0 STEP(0 1 0)\nR1 1 0 1"))
    assert compare_ngspice.compatible(parse("V1 1 0 1\nR1 1 0 1"))


@pytest.mark.skipif(compare_ngspice.find_ngspice() is None, reason="ngspice is not installed")
def test_examples_match_ngspice():
    rows = compare_ngspice.compare(compare_ngspice.find_ngspice())
    assert rows, "no comparable examples were found"
    for name, node, ours, theirs, diff in rows:
        assert diff <= 1e-3 * max(abs(theirs), 1e-3), f"{name} node {node}: MiniSpice {ours}, ngspice {theirs}"
