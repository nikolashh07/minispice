"""The browser's door into the engine.

The web app runs this same Python package inside the page with Pyodide. JavaScript calls these
functions with plain strings and numbers and gets back a JSON string, so the boundary between the
two languages stays simple: no Python objects ever cross into JavaScript. Every function catches
MiniSpice's own errors and returns them as {"ok": false, "error": "..."} for the page to show.

Only numpy is needed here (no matplotlib or schemdraw), which keeps the browser download small.
"""

import json
import math

import numpy as np

from .analysis.dc import operating_point
from .errors import MiniSpiceError
from .netlist import parse
from .power import power_report

MAX_POINTS = 2000  # waveforms are resampled to at most this many points before going to the page


def _respond(fn):
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            result["ok"] = True
        except MiniSpiceError as error:
            result = {"ok": False, "error": str(error)}
        except (ValueError, KeyError, IndexError) as error:
            result = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        return json.dumps(result, default=_clean)

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _clean(value):
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return [_finite(v) for v in value.tolist()]
    raise TypeError(f"can't send {type(value).__name__} to the page")


def _finite(value):
    # JSON has no NaN or infinity.
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


@_respond
def solve(netlist):
    """DC operating point: node voltages, and the voltage, current, power and region of every part."""
    circuit = parse(netlist)
    solution = operating_point(circuit)
    report = power_report(solution)
    parts = []
    for comp in circuit.components:
        currents = comp.terminal_currents(solution.x, solution.ctx)
        parts.append({
            "name": comp.name,
            "kind": comp.kind,
            "nodes": list(comp.nodes),
            "terminals": list(comp.terminals),
            "currents": [float(c) for c in currents],
            "voltage": float(comp.voltage(solution.x)) if len(comp.nodes) >= 2 else 0.0,
            "power": float(comp.power(solution.x, solution.ctx)),
            "region": comp.region(solution.x, solution.ctx),
            "rating": getattr(comp, "rating", None),
        })
    return {
        "title": circuit.title,
        "nodes": solution.node_voltages,
        "parts": parts,
        "power": {"delivered": report.delivered, "absorbed": report.absorbed, "balanced": report.balanced},
        "warnings": circuit.warnings + report.warnings,
        "iterations": solution.iterations,
    }


@_respond
def transient(netlist, t_step, t_stop, probes):
    """Waveforms for the oscilloscope. probes is a list like ["v(out)", "i(R1)"]."""
    from .analysis.transient import transient as run

    circuit = parse(netlist)
    result = run(circuit, float(t_stop), float(t_step))
    points = min(MAX_POINTS, max(2, int(round(float(t_stop) / float(t_step))) + 1))
    grid = np.linspace(0.0, float(t_stop), points)
    series = {p: np.interp(grid, result.times, result.measure(p)) for p in probes}
    return {"times": grid, "series": series}


@_respond
def ac(netlist, input_source, f_start, f_stop, points_per_decade, probes):
    """Bode data: magnitude in dB and phase in degrees for each probe, with input_source driven by 1 V AC."""
    from .analysis.ac import ac_analysis, db, phase_degrees

    circuit = parse(netlist)
    for comp in circuit.independent_sources:
        comp.ac = 0j
    circuit.get(input_source).ac = 1.0 + 0j
    result = ac_analysis(circuit, float(f_start), float(f_stop), float(points_per_decade), "dec")
    return {
        "freqs": result.freqs,
        "magnitude_db": {p: db(result.measure(p)) for p in probes},
        "phase": {p: phase_degrees(result.measure(p)) for p in probes},
    }


@_respond
def spectrum(netlist, t_step, t_stop, probe):
    """Spectrum analyzer: amplitude of each frequency in a transient waveform."""
    from .analysis.fourier import spectrum as fft
    from .analysis.transient import transient as run

    result = run(parse(netlist), float(t_stop), float(t_step))
    freqs, amps = fft(result.times, result.measure(probe))
    keep = slice(0, min(len(freqs), MAX_POINTS))
    return {"freqs": freqs[keep], "amplitudes": amps[keep]}


@_respond
def explain(netlist):
    """The explain-mode walkthrough, with the parts to highlight at each step."""
    from .explain import explain_dc

    walkthrough, _ = explain_dc(parse(netlist))
    return walkthrough.to_dict()


@_respond
def check(netlist):
    """Parse only: lets the editor flag netlist mistakes as the user types."""
    circuit = parse(netlist)
    return {"title": circuit.title, "nodes": circuit.nodes, "parts": [c.name for c in circuit.components]}


FUNCTIONS = {"solve": solve, "transient": transient, "ac": ac, "spectrum": spectrum, "explain": explain, "check": check}


def call(name, args_json):
    """Single entry point for the browser: a function name and its arguments as a JSON list.

    Passing JSON text both ways means the browser never holds a Python object and Python never
    holds a JavaScript one, which is the simplest way to keep the two languages apart.
    """
    fn = FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"ok": False, "error": f"the engine has no function '{name}'"})
    return fn(*json.loads(args_json))
