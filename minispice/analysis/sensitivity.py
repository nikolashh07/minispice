"""Sensitivity analysis: which parts affect the output the most?

For every part, nudge its value up and down by a tiny amount and see how much the output moves.
The normalized sensitivity (% change of output per % change of the part) can be compared across
parts of any type, so the ranked list tells a designer where tight tolerances are worth paying for.
"""

from dataclasses import dataclass

from ..errors import CircuitError
from .dc import operating_point


@dataclass
class Sensitivity:
    name: str
    kind: str
    value: float
    derivative: float  # d(output) / d(value)
    normalized: float  # (d output / output) / (d value / value)


def default_measure(expr):
    return lambda circuit: operating_point(circuit).measure(expr)


def sensitivity(circuit, expr, parts=None, relative_step=1e-6, measure=None):
    """Ranked list of Sensitivity, most influential part first."""
    measure = measure or default_measure(expr)
    y0 = measure(circuit)
    if parts is None:
        parts = [c.name for c in circuit.components if isinstance(c.value, (int, float)) and c.value not in (0, None)]
    results = []
    for name in parts:
        comp = circuit.get(name)
        p = comp.value
        if p is None or p == 0:
            raise CircuitError(f"{comp.name} has no nonzero value to vary")
        dp = abs(p) * relative_step
        # Central difference: the error of the slope estimate shrinks with dp², not dp.
        y_up = measure(circuit.with_value(name, p + dp))
        y_down = measure(circuit.with_value(name, p - dp))
        derivative = (y_up - y_down) / (2 * dp)
        normalized = derivative * p / y0 if y0 != 0 else float("nan")
        results.append(Sensitivity(comp.name, comp.kind, p, derivative, normalized))
    # Rank by normalized sensitivity; fall back to the absolute effect of a 1 % change if y0 = 0.
    results.sort(key=lambda s: -abs(s.normalized if s.normalized == s.normalized else s.derivative * s.value))
    return results
