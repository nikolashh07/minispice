"""Tolerances, Monte Carlo and worst-case analysis.

Real parts aren't exactly their marked value: a 5 % resistor can be anywhere from 0.95× to 1.05×.
Monte Carlo builds hundreds of random copies of the circuit within those tolerances and collects
the results, which shows the spread a production run would really have. Worst case finds the
extreme results by pushing every part to the end of its range that hurts most.
"""

import itertools
from dataclasses import dataclass

import numpy as np

from ..errors import CircuitError
from .sensitivity import default_measure, sensitivity

MAX_EXHAUSTIVE_PARTS = 10  # 2^10 = 1024 corners; beyond that use sensitivities to pick the corner


@dataclass
class MonteCarloResult:
    expr: str
    nominal: float
    values: np.ndarray

    @property
    def mean(self):
        return float(np.mean(self.values))

    @property
    def std(self):
        return float(np.std(self.values, ddof=1)) if len(self.values) > 1 else 0.0

    @property
    def low(self):
        return float(np.min(self.values))

    @property
    def high(self):
        return float(np.max(self.values))

    def fraction_within(self, low, high):
        """Yield: the fraction of builds whose output lands inside [low, high]."""
        return float(np.mean((self.values >= low) & (self.values <= high)))


def toleranced_parts(circuit):
    parts = [c for c in circuit.components if c.tol]
    if not parts:
        raise CircuitError("No parts have a tolerance. Add one to a part line, like 'R1 1 2 1k tol=5%'.")
    return parts


def monte_carlo(circuit, expr, runs=200, seed=1, distribution="uniform", measure=None):
    """Random builds of the circuit. 'uniform' spreads values evenly over ±tol; 'gaussian' uses
    a normal distribution with ±tol at 3 standard deviations, clipped to ±tol."""
    if runs < 1:
        raise CircuitError("Monte Carlo needs at least one run.")
    measure = measure or default_measure(expr)
    parts = toleranced_parts(circuit)
    rng = np.random.default_rng(seed)
    nominal = measure(circuit)
    values = []
    for _ in range(runs):
        work = circuit.copy()
        for part in parts:
            if distribution == "gaussian":
                spread = np.clip(rng.normal(0, part.tol / 3), -part.tol, part.tol)
            elif distribution == "uniform":
                spread = rng.uniform(-part.tol, part.tol)
            else:
                raise CircuitError("distribution must be 'uniform' or 'gaussian'")
            work.get(part.name).value = part.value * (1 + spread)
        values.append(measure(work))
    return MonteCarloResult(expr, nominal, np.array(values))


@dataclass
class WorstCase:
    expr: str
    nominal: float
    low: float
    high: float
    low_corner: dict  # part name -> value used
    high_corner: dict
    method: str  # "all corners" or "sensitivity"


def worst_case(circuit, expr, measure=None):
    measure = measure or default_measure(expr)
    parts = toleranced_parts(circuit)
    nominal = measure(circuit)

    def build(signs):
        work = circuit.copy()
        corner = {}
        for part, sign in zip(parts, signs):
            value = part.value * (1 + sign * part.tol)
            work.get(part.name).value = value
            corner[part.name] = value
        return measure(work), corner

    if len(parts) <= MAX_EXHAUSTIVE_PARTS:
        results = [build(signs) for signs in itertools.product((-1, 1), repeat=len(parts))]
        method = "all corners"
    else:
        # Too many corners to try: push each part in the direction its sensitivity says raises
        # (or lowers) the output. Exact whenever the output changes monotonically with each part.
        slopes = {s.name: s.derivative for s in sensitivity(circuit, expr, [p.name for p in parts], measure=measure)}
        up = [1 if slopes[p.name] >= 0 else -1 for p in parts]
        results = [build(up), build([-s for s in up])]
        method = "sensitivity"
    low = min(results, key=lambda r: r[0])
    high = max(results, key=lambda r: r[0])
    return WorstCase(expr, nominal, low[0], high[0], low[1], high[1], method)
