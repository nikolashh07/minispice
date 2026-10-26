"""Every circuit in examples/ states its expected answers in comments, and this test checks them all.

    * expect: v(2) = 5                 DC operating point (default tolerance 0.1 %)
    * expect: i(V1) = -5m tol=1%
"""

import pathlib
import re

import pytest

from minispice import load, operating_point, parse_value

EXAMPLES = sorted(pathlib.Path(__file__).parent.parent.joinpath("examples").glob("*.cir"))
EXPECT = re.compile(r"^\*\s*expect:\s*(.+?)\s*=\s*(\S+)(?:\s+tol=(\S+))?\s*$", re.I)


def expectations(path):
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = EXPECT.match(line.strip())
        if match:
            probe, value, tol = match.groups()
            found.append((probe, parse_value(value), parse_value(tol) if tol else 1e-3))
    return found


def test_there_are_examples():
    assert len(EXAMPLES) >= 4


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example(path):
    checks = expectations(path)
    circuit = load(str(path))
    if not checks:
        pytest.skip("no DC expectations in this example")
    solution = operating_point(circuit)
    for probe, expected, tol in checks:
        got = solution.measure(probe)
        assert got == pytest.approx(expected, rel=tol, abs=1e-12), f"{path.name}: {probe}"
