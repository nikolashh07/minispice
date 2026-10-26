"""Every circuit in examples/ states its expected answers in comments, and this test checks them all.

    * expect: v(2) = 5                          DC operating point (default tolerance 0.1 %)
    * expect: i(V1) = -5m tol=1%
    * expect-tran: v(2) at 1m = 3.1606          transient value at a time (uses the netlist's .tran)
    * expect-ac: vdb(2) at 159.155 = -3.0103    AC value at a frequency (uses the netlist's .ac)
"""

import pathlib
import re

import pytest

from minispice import load, operating_point, parse_value
from minispice.analysis.ac import ac_from_directive
from minispice.analysis.transient import run_settings, settings_from_directive

EXAMPLES = sorted(pathlib.Path(__file__).parent.parent.joinpath("examples").glob("*.cir"))
EXPECT = re.compile(r"^\*\s*expect(-tran|-ac)?:\s*(.+?)(?:\s+at\s+(\S+))?\s*=\s*(\S+)(?:\s+tol=(\S+))?\s*$", re.I)


def expectations(path):
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = EXPECT.match(line.strip())
        if match:
            kind, probe, at, value, tol = match.groups()
            found.append(((kind or "").lstrip("-").lower() or "op", probe, parse_value(at) if at else None,
                          parse_value(value), parse_value(tol) if tol else 1e-3))
    return found


def test_there_are_examples():
    assert len(EXAMPLES) >= 10


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example(path):
    checks = expectations(path)
    circuit = load(str(path))
    if not checks:
        pytest.skip("this example has no stated answers (it is checked in its own test file)")
    results = {}
    for kind, probe, at, expected, tol in checks:
        if kind not in results:
            if kind == "op":
                results[kind] = operating_point(circuit)
            elif kind == "tran":
                results[kind] = run_settings(circuit, settings_from_directive(circuit.find_directives("tran")[0]))
            else:
                results[kind] = ac_from_directive(circuit, circuit.find_directives("ac")[0])
        result = results[kind]
        got = result.measure(probe) if kind == "op" else result.at(probe, at)
        assert got == pytest.approx(expected, rel=tol, abs=1e-12), f"{path.name}: {probe}"
