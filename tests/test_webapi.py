"""The JSON API the browser app calls through Pyodide (Part F)."""

import json

import pytest

from minispice import webapi

DIVIDER = "V1 1 0 10\nR1 1 2 1k\nR2 2 0 1k\n"


def call(fn, *args):
    return json.loads(fn(*args))


def test_solve():
    data = call(webapi.solve, DIVIDER)
    assert data["ok"]
    assert data["nodes"] == {"1": 10.0, "2": 5.0}
    r1 = next(p for p in data["parts"] if p["name"] == "R1")
    assert r1["currents"] == pytest.approx([5e-3, -5e-3])
    assert r1["power"] == pytest.approx(25e-3)
    assert data["power"]["balanced"]


def test_errors_come_back_as_messages():
    data = call(webapi.solve, "V1 1 0 10\nR1 1 2\n")
    assert data == {"ok": False, "error": data["error"]}
    assert "line 2" in data["error"]
    assert call(webapi.solve, "V1 1 0 1\nV2 1 0 2\nR1 1 0 1")["ok"] is False


def test_transient_is_resampled():
    data = call(webapi.transient, "V1 1 0 STEP(0 5 0)\nR1 1 2 1k\nC1 2 0 1u\n", 1e-5, 5e-3, ["v(2)"])
    assert len(data["times"]) == 501
    assert data["series"]["v(2)"][100] == pytest.approx(5 * (1 - 2.718281828 ** -1), rel=2e-3)


def test_ac_drives_the_chosen_source():
    data = call(webapi.ac, "V1 1 0 0\nR1 1 2 1k\nC1 2 0 1u\n", "V1", 1, 1e5, 10, ["v(2)"])
    assert data["ok"]
    assert data["magnitude_db"]["v(2)"][0] == pytest.approx(0, abs=0.01)
    assert data["magnitude_db"]["v(2)"][-1] < -50


def test_spectrum_and_explain():
    data = call(webapi.spectrum, "V1 1 0 SIN(0 1 1k)\nR1 1 0 1k\n", 1e-5, 10e-3, "v(1)")
    peak = max(range(1, len(data["amplitudes"])), key=lambda k: data["amplitudes"][k])
    assert data["freqs"][peak] == pytest.approx(1e3, rel=0.05)
    steps = call(webapi.explain, DIVIDER)["steps"]
    assert steps[0]["title"] == "Choose the unknowns"


def test_check_and_no_plotting_imports():
    assert call(webapi.check, DIVIDER)["parts"] == ["V1", "R1", "R2"]
    # The browser bundle doesn't ship matplotlib, so the web API must never import it.
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(webapi))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("plotting" in m or "schematic" in m for m in imported)


def test_single_entry_point():
    assert json.loads(webapi.call("solve", json.dumps([DIVIDER])))["nodes"]["2"] == 5.0
    assert json.loads(webapi.call("nope", "[]"))["ok"] is False
