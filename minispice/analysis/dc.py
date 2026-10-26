"""DC analysis: the operating point, where nothing changes with time.

Capacitors are open circuits and inductors are short circuits. A linear circuit needs one matrix
solve. A circuit with diodes or transistors needs Newton's method: guess, replace each nonlinear
part with its tangent line at the guess, solve, and repeat until the answer stops changing.
"""

import numpy as np

from ..context import Context
from ..errors import ConvergenceError
from ..mna import Layout, assemble, check_dc_topology
from ..results import Solution

RELTOL = 1e-3
VNTOL = 1e-6  # volts
ABSTOL = 1e-12  # amps


def operating_point(circuit, recorder=None, x0=None, temperature=None, sources_on=None, sparse=None):
    """Solve the circuit's DC operating point and return a Solution."""
    check_dc_topology(circuit)
    layout = Layout(circuit)
    ctx = Context(
        mode="dc",
        temperature=circuit.temperature if temperature is None else temperature,
        sources_on=sources_on,
    )
    x, iterations = solve_dc(circuit.components, layout, ctx, x0, sparse)
    ctx.x = x
    if recorder is not None:
        record_solve(circuit.components, layout, ctx, x, iterations, recorder)
    return Solution(circuit, layout, x, ctx, iterations)


def record_solve(components, layout, ctx, x, iterations, recorder):
    """Re-stamp once at the answer with the recorder on, so explain mode sees every law used."""
    ctx.recorder = recorder
    ctx.x = x
    system = assemble(components, layout, ctx)
    ctx.recorder = None
    recorder.capture(layout, system, x, iterations)


def newton(components, layout, ctx, x0, max_iter=100, sparse=None):
    """Newton-Raphson iteration. Returns (solution, iterations). A linear circuit takes one solve."""
    x = np.zeros(layout.size) if x0 is None else np.array(x0, dtype=float)
    linear = not any(c.nonlinear for c in components)
    n_nodes = len(layout.nodes)
    for iteration in range(1, max_iter + 1):
        ctx.x = x
        ctx.limited = False
        system = assemble(components, layout, ctx)
        if ctx.gshunt:
            for row in range(n_nodes):
                system.add(row, row, ctx.gshunt)
        x_new = system.solve(layout, sparse)
        if linear:
            return x_new, 1
        if not ctx.limited and converged(x_new, x, n_nodes):
            # Newton's error shrinks quadratically, so one more step for the price of one solve
            # leaves KCL satisfied to near machine precision (and the power balance exact).
            ctx.x = x_new
            system = assemble(components, layout, ctx)
            if ctx.gshunt:
                for row in range(n_nodes):
                    system.add(row, row, ctx.gshunt)
            return system.solve(layout, sparse), iteration + 1
        x = x_new
    raise ConvergenceError(f"Newton's method did not converge in {max_iter} iterations")


def converged(x_new, x_old, n_nodes):
    tol = RELTOL * np.maximum(np.abs(x_new), np.abs(x_old))
    tol[:n_nodes] += VNTOL
    tol[n_nodes:] += ABSTOL
    return bool(np.all(np.abs(x_new - x_old) <= tol))


def solve_dc(components, layout, ctx, x0=None, sparse=None):
    """Newton's method, with two standard rescue strategies if it fails on its own."""
    try:
        ctx.limits = {}
        return newton(components, layout, ctx, x0, sparse=sparse)
    except ConvergenceError:
        pass

    # gmin stepping: start with every node leaking to ground through a big conductance, which
    # makes the problem easy, then shrink it, using each answer as the next starting guess.
    try:
        ctx.limits = {}
        x = x0
        for gshunt in [1e-2 / 10**k for k in range(11)]:
            ctx.gshunt = gshunt
            x, _ = newton(components, layout, ctx, x, sparse=sparse)
        ctx.gshunt = 0.0
        return newton(components, layout, ctx, x, sparse=sparse)
    except ConvergenceError:
        ctx.gshunt = 0.0

    # Source stepping: ramp every source up from 0 %, where the answer is trivially all zeros.
    try:
        ctx.limits = {}
        x = None
        total = 0
        for scale in np.linspace(0.05, 1.0, 20):
            ctx.source_scale = scale
            x, iterations = newton(components, layout, ctx, x, sparse=sparse)
            total += iterations
        return x, total
    except ConvergenceError:
        pass
    finally:
        ctx.source_scale = 1.0

    raise ConvergenceError(
        "Could not find the DC operating point: Newton's method failed, even with gmin stepping and "
        "source stepping. Check for parts that make the circuit impossible (for example a current "
        "source forcing current into a reverse-biased diode), unrealistic model values, or a "
        "transistor with nothing to limit its current."
    )
