"""Sweeps: rerun an analysis while one value changes.

DC sweep: step a source (or any part's value, or the temperature) and solve the operating point at
each value. Sweeping the voltage across a diode or transistor draws its characteristic curve.
Parameter sweep: rerun any analysis for a list of values of one part.
"""

from dataclasses import dataclass

import numpy as np

from ..errors import CircuitError
from ..units import parse_value
from .dc import operating_point


def sweep_values(start, stop, step):
    if step == 0:
        raise CircuitError("The sweep step can't be zero.")
    if (stop - start) / step < 0:
        step = -step  # let "0 5 -0.1" and "5 0 0.1" mean the obvious thing
    count = int(np.floor((stop - start) / step + 1e-9)) + 1
    return start + step * np.arange(count)


def set_value(circuit, name, value):
    """Change a part's main value, or the circuit temperature if name is 'temp'."""
    if name.lower() == "temp":
        circuit.temperature = value
        return
    comp = circuit.get(name)
    if comp.value is None:
        raise CircuitError(f"{comp.name} has no single value to sweep")
    comp.value = value


@dataclass
class SweepResult:
    name: str
    values: np.ndarray
    solutions: list

    def measure(self, expr):
        return np.array([s.measure(expr) for s in self.solutions])


def dc_sweep(circuit, name, values):
    """Operating point at each value. Each solve starts from the previous answer (continuation),
    which keeps Newton's method on track through sharp bends like a diode turning on."""
    solutions = []
    x = None
    for value in values:
        work = circuit.copy()
        set_value(work, name, float(value))
        solution = operating_point(work, x0=x)
        x = solution.x
        solutions.append(solution)
    display = name if name.lower() == "temp" else circuit.get(name).name
    return SweepResult(display, np.asarray(values, dtype=float), solutions)


def parameter_sweep(circuit, name, values, run):
    """[(value, run(modified circuit))] for each value. run is any analysis, e.g. operating_point."""
    out = []
    for value in values:
        work = circuit.copy()
        set_value(work, name, float(value))
        out.append((float(value), run(work)))
    return out


def dc_from_directive(circuit, directive):
    args = directive.args
    if len(args) < 4:
        raise CircuitError("Usage: .dc <source or part or temp> <start> <stop> <step>")
    return dc_sweep(circuit, args[0], sweep_values(*(parse_value(a) for a in args[1:4])))


def step_values(directive_args):
    """'.step R1 list 1k 2k 5k' or '.step R1 1k 10k 1k' -> (name, values)."""
    if len(directive_args) < 2:
        raise CircuitError("Usage: .step <part> list <v1> <v2> ...   or   .step <part> <start> <stop> <step>")
    name = directive_args[0]
    rest = directive_args[1:]
    if rest[0] == "list":
        return name, [parse_value(v) for v in rest[1:]]
    if len(rest) != 3:
        raise CircuitError("Usage: .step <part> <start> <stop> <step>")
    return name, list(sweep_values(*(parse_value(v) for v in rest)))
