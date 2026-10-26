"""Transient analysis: steps through time using companion models.

At every time step each capacitor and inductor is replaced by a resistor plus a current source
that mimics it over that step, which turns the problem back into a DC solve. Two integration
methods are available:

  backward Euler ("be")  first-order accurate, very stable, but it drains energy from
                         oscillators, so ringing dies out faster than it should
  trapezoidal ("trap")   second-order accurate and energy-preserving for LC circuits

With adaptive stepping, each step is also taken as two half steps. The difference between the two
answers estimates the error, so the step shrinks where signals change fast and grows where they don't.
"""

from dataclasses import dataclass

import numpy as np

from ..components.base import Component
from ..context import Context
from ..errors import CircuitError, ConvergenceError
from ..mna import Layout, check_dc_topology
from ..results import parse_probe
from .dc import newton, solve_dc

RELTOL = 1e-3
VNTOL = 1e-6
ABSTOL = 1e-9


@dataclass
class TransientSettings:
    t_stop: float
    t_step: float = None  # printing / maximum step
    t_start: float = 0.0
    t_max: float = None
    method: str = "trap"
    adaptive: bool = True
    uic: bool = False
    reltol: float = RELTOL


class TransientResult:
    def __init__(self, circuit, layout, times, solutions, states, temperature):
        self.circuit = circuit
        self.layout = layout
        self.times = np.array(times)
        self.X = np.array(solutions)
        self.states = states
        self.temperature = temperature

    def _ctx(self, k):
        return Context(mode="tran", time=self.times[k], state=self.states[k], temperature=self.temperature)

    def v(self, node, ref="0"):
        return self._node(node) - self._node(ref)

    def _node(self, node):
        from ..netlist import normalize_node

        node = normalize_node(str(node))
        if node == "0":
            return np.zeros(len(self.times))
        if node not in self.layout.node_index:
            raise CircuitError(f"There is no node '{node}'. Nodes: {', '.join(self.layout.nodes)}")
        return self.X[:, self.layout.node_index[node]]

    def i(self, name, terminal=0):
        comp = self.circuit.get(name)
        if isinstance(terminal, str):
            terminal = [t.lower() for t in comp.terminals].index(terminal.lower())
        return np.array([comp.terminal_currents(x, self._ctx(k))[terminal] for k, x in enumerate(self.X)], dtype=float)

    def p(self, name):
        comp = self.circuit.get(name)
        return np.array([comp.power(x, self._ctx(k)) for k, x in enumerate(self.X)], dtype=float)

    def energy(self, name):
        """Energy absorbed by a part over the whole run, in joules (area under its power curve)."""
        return float(np.trapezoid(self.p(name), self.times))

    def measure(self, expr):
        kind, first, second = parse_probe(expr)
        if kind == "v":
            return self.v(first, second)
        if kind == "i":
            return self.i(first, second or 0)
        if kind == "p":
            return self.p(first)
        raise CircuitError(f"'{expr}' is an AC quantity; transient results have v(), i() and p()")

    def at(self, expr, t):
        """Value of a probe at time t, interpolating between time points."""
        return float(np.interp(t, self.times, self.measure(expr)))

    def uniform(self, expr, dt):
        """Probe values resampled on an even time grid (for printing, plotting and FFT)."""
        grid = np.arange(self.times[0], self.times[-1] + dt / 2, dt)
        return grid, np.interp(grid, self.times, self.measure(expr))


def transient(circuit, t_stop, t_step=None, t_start=0.0, t_max=None, method="trap", adaptive=True, uic=False, reltol=RELTOL):
    if t_stop <= 0:
        raise CircuitError("The transient stop time must be positive.")
    if method not in ("be", "trap"):
        raise CircuitError("Integration method must be 'be' (backward Euler) or 'trap' (trapezoidal).")
    t_step = t_step or t_stop / 100
    h_max = t_max or t_step
    h_min = t_stop * 1e-14

    layout = Layout(circuit)
    components = circuit.components
    ctx = Context(mode="dc", temperature=circuit.temperature, uic=uic, transient_op=True)
    x0 = _initial_point(circuit, layout, ctx, uic)
    ctx.transient_op = False
    stateful = [c for c in components if c.initial_state(x0, ctx) is not None]
    states = {c.key: c.initial_state(x0, ctx) for c in stateful}

    breaks = sorted({t for c in components for t in c.breakpoints(t_stop) if 0 < t < t_stop} | {t_stop})
    times, solutions, history = [0.0], [x0], [dict(states)]
    t, x = 0.0, x0
    # Right after t = 0 or a sudden jump (an edge), signals change fastest, so the first step there
    # is short and uses backward Euler. Trapezoidal integration would reuse the capacitor current
    # from just before the jump, which is wrong after it, and the error would ring on for many steps.
    first_step = h_max / 100 if adaptive else h_max / 10
    h = first_step
    after_break = True
    ctx.mode = "tran"

    # Times closer than this count as the same instant, so rounding in t + h + h + ... can't
    # leave a uselessly tiny step just before a breakpoint.
    eps = 1e-6 * h_max
    while t < t_stop - eps:
        next_break = next(b for b in breaks if b > t + eps)
        h = min(h, h_max)
        if t + h > next_break - eps:
            h = next_break - t
        step_method = "be" if after_break else method
        try:
            if adaptive:
                x_full, _ = _step(components, layout, ctx, x, states, t, h, step_method, stateful)
                x_half, s_half = _step(components, layout, ctx, x, states, t, h / 2, step_method, stateful)
                x_new, s_new = _step(components, layout, ctx, x_half, s_half, t + h / 2, h / 2, step_method, stateful)
                order = 1 if step_method == "be" else 2
                # Richardson: the error left in the half-step answer is about diff / (2^order - 1).
                err = _error_norm(x_new, x_full, len(layout.nodes), reltol) / (2 ** order - 1)
                if err > 1.0 and h > h_min * 10:
                    h *= max(0.2, 0.9 * err ** (-1.0 / (order + 1)))
                    continue
                grow = min(2.0, 0.9 * err ** (-1.0 / (order + 1))) if err > 0 else 2.0
            else:
                x_new, s_new = _step(components, layout, ctx, x, states, t, h, step_method, stateful)
                grow = 1.0
        except ConvergenceError:
            h /= 8
            if h < h_min:
                raise ConvergenceError(f"Transient analysis got stuck at t = {t:.4g} s: the time step became too small. "
                                       "Check for an unrealistic part value or a circuit that has no stable solution.")
            continue

        t_new = t + h
        if abs(t_new - next_break) <= eps:
            t_new = next_break
        t, x, states = t_new, x_new, s_new
        times.append(t)
        solutions.append(x)
        history.append(dict(states))

        after_break = t == next_break and t < t_stop
        if after_break:
            h = first_step
        else:
            h = h * grow if adaptive else h_max

    result = TransientResult(circuit, layout, times, solutions, history, circuit.temperature)
    if t_start > 0:
        keep = result.times >= t_start
        result.times, result.X = result.times[keep], result.X[keep]
        result.states = [s for s, k in zip(result.states, keep) if k]
    return result


def _step(components, layout, ctx, x, states, t, h, method, stateful):
    ctx.time = t + h
    ctx.h = h
    ctx.method = method
    ctx.state = states
    ctx.x_prev = x
    x_new, _ = newton(components, layout, ctx, x)
    new_states = {c.key: c.update_state(x_new, ctx) for c in stateful}
    return x_new, new_states


def _error_norm(a, b, n_nodes, reltol):
    tol = reltol * np.maximum(np.abs(a), np.abs(b))
    tol[:n_nodes] += VNTOL
    tol[n_nodes:] += ABSTOL
    return float(np.max(np.abs(a - b) / tol)) if len(a) else 0.0


class _InitialCondition(Component):
    """Holds a node near its .ic voltage during the t = 0 solve, through a very small resistor."""

    G = 1e4

    def __init__(self, node, volts):
        super().__init__(f"ic_{node}", [node, "0"])
        self.value = volts

    def dc_paths(self):
        return [tuple(self.nodes)]

    def stamp(self, system, ctx):
        system.conductance(self.idx[0], -1, self.G)
        system.add_b(self.idx[0], self.G * self.value)

    def terminal_currents(self, x, ctx):
        return [0.0, 0.0]


def _initial_point(circuit, layout, ctx, uic):
    if uic:
        # Skip the DC solve: every node starts at 0 V unless .ic says otherwise, and each
        # capacitor and inductor starts at its ic= value.
        x0 = np.zeros(layout.size)
        for node, volts in circuit.initial_conditions.items():
            if node in layout.node_index:
                x0[layout.node_index[node]] = volts
        return x0
    if circuit.initial_conditions:
        held = circuit.copy()
        for node, volts in circuit.initial_conditions.items():
            if node not in layout.node_index:
                raise CircuitError(f".ic sets node '{node}', which isn't in the circuit")
            held.add(_InitialCondition(node, volts))
        check_dc_topology(held)
        held_layout = Layout(held)
        x0, _ = solve_dc(held.components, held_layout, ctx)
        Layout(circuit)  # re-bind the original parts to their own layout
        return x0
    check_dc_topology(circuit)
    x0, _ = solve_dc(circuit.components, layout, ctx)
    return x0


def settings_from_directive(directive):
    """Read '.tran tstep tstop [tstart [tmax]] [uic]' plus MiniSpice options method= and fixed."""
    from ..units import parse_value

    args = [a for a in directive.args if a not in ("uic", "fixed")]
    if len(args) < 2:
        raise CircuitError(".tran needs a step and a stop time: .tran <tstep> <tstop> [tstart [tmax]] [uic]")
    values = [parse_value(a) for a in args]
    method = directive.keywords.get("method", "trap")
    method = {"euler": "be", "gear": "be", "trapezoidal": "trap"}.get(method, method)
    return TransientSettings(
        t_step=values[0],
        t_stop=values[1],
        t_start=values[2] if len(values) > 2 else 0.0,
        t_max=values[3] if len(values) > 3 else None,
        method=method,
        adaptive="fixed" not in directive.args,
        uic="uic" in directive.args,
    )


def run_settings(circuit, settings):
    return transient(
        circuit, settings.t_stop, settings.t_step, settings.t_start, settings.t_max,
        settings.method, settings.adaptive, settings.uic, settings.reltol,
    )
