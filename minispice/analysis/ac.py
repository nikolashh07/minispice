"""AC analysis: frequency sweeps using complex impedances.

A sine wave at one frequency can be written as a phasor, a complex number holding its amplitude
and phase. Then d/dt becomes multiplication by jω, so a capacitor behaves like a resistor of
1/(jωC) and an inductor like jωL. The whole circuit becomes a linear system with complex numbers,
solved once per frequency with the same MNA machinery as DC.
"""

import numpy as np

from ..context import Context
from ..errors import CircuitError
from ..mna import Layout, assemble
from ..results import parse_probe
from ..units import parse_value


def frequencies(sweep, points, f_start, f_stop):
    if f_start <= 0 or f_stop <= f_start:
        raise CircuitError("AC sweep needs 0 < fstart < fstop")
    sweep = sweep.lower()
    if sweep == "lin":
        return np.linspace(f_start, f_stop, max(int(points), 2))
    if sweep in ("dec", "oct"):
        base = 10.0 if sweep == "dec" else 2.0
        count = int(round(points * np.log(f_stop / f_start) / np.log(base))) + 1
        return np.logspace(np.log10(f_start), np.log10(f_stop), max(count, 2))
    raise CircuitError(f"AC sweep type must be dec, oct or lin, not '{sweep}'")


class ACResult:
    def __init__(self, circuit, layout, freqs, solutions, x_op, temperature):
        self.circuit = circuit
        self.layout = layout
        self.freqs = np.asarray(freqs)
        self.X = np.asarray(solutions)
        self.x_op = x_op
        self.temperature = temperature

    def v(self, node, ref="0"):
        return self._node(node) - self._node(ref)

    def _node(self, node):
        from ..netlist import normalize_node

        node = normalize_node(str(node))
        if node == "0":
            return np.zeros(len(self.freqs), dtype=complex)
        if node not in self.layout.node_index:
            raise CircuitError(f"There is no node '{node}'. Nodes: {', '.join(self.layout.nodes)}")
        return self.X[:, self.layout.node_index[node]]

    def i(self, name, terminal=0):
        comp = self.circuit.get(name)
        out = []
        for f, x in zip(self.freqs, self.X):
            ctx = Context(mode="ac", omega=2 * np.pi * f, x_op=self.x_op, temperature=self.temperature)
            out.append(comp.ac_terminal_currents(x, ctx)[terminal])
        return np.array(out, dtype=complex)

    def measure(self, expr):
        """Complex phasor for v()/i(), or a real number for vdb/vp (dB and phase in degrees)."""
        kind, first, second = parse_probe(expr)
        if kind in ("v", "vm", "vr", "vi", "vdb", "vp"):
            value = self.v(first, second)
        elif kind in ("i", "im", "ip", "idb"):
            value = self.i(first)
        else:
            raise CircuitError(f"'{expr}': AC results have v(), vdb(), vp(), i()")
        suffix = kind[1:]
        if suffix == "m":
            return np.abs(value)
        if suffix == "r":
            return value.real
        if suffix == "i":
            return value.imag
        if suffix == "db":
            return db(value)
        if suffix == "p":
            return phase_degrees(value)
        return value

    def at(self, expr, f):
        """Interpolate a real-valued probe (like vdb(out)) at frequency f, on a log-frequency axis."""
        values = self.measure(expr)
        if np.iscomplexobj(values):
            values = np.abs(values)
        return float(np.interp(np.log10(f), np.log10(self.freqs), values))

    def corner_frequency(self, expr, drop_db=3.0103):
        """First frequency where v(...) falls drop_db below its value at the lowest frequency."""
        mag = db(self.measure(expr))
        target = mag[0] - drop_db
        below = np.nonzero(mag <= target)[0]
        if len(below) == 0 or below[0] == 0:
            return None
        k = below[0]
        # Interpolate on log frequency between the two points that straddle the target.
        f0, f1 = np.log10(self.freqs[k - 1]), np.log10(self.freqs[k])
        m0, m1 = mag[k - 1], mag[k]
        return float(10 ** (f0 + (target - m0) * (f1 - f0) / (m1 - m0)))


def db(value):
    return 20 * np.log10(np.maximum(np.abs(value), 1e-300))


def phase_degrees(value):
    # Unwrap so a phase that keeps falling past -180° reads -200°, not +160°.
    return np.degrees(np.unwrap(np.angle(value)))


def ac_analysis(circuit, f_start, f_stop, points=10, sweep="dec", sources_on=None):
    from .dc import operating_point

    if not any(getattr(c, "ac", 0) for c in circuit.components if c.is_source) and sources_on is None:
        raise CircuitError("AC analysis needs a source with an AC value, like 'V1 in 0 DC 0 AC 1'.")
    # Nonlinear parts are replaced by their small-signal (tangent) model at the DC operating point.
    x_op = None
    if not circuit.is_linear:
        x_op = operating_point(circuit).x
    layout = Layout(circuit)
    freqs = frequencies(sweep, points, f_start, f_stop)
    solutions = []
    for f in freqs:
        ctx = Context(mode="ac", omega=2 * np.pi * f, x_op=x_op, temperature=circuit.temperature, sources_on=sources_on)
        system = assemble(circuit.components, layout, ctx, dtype=complex)
        solutions.append(system.solve(layout))
    return ACResult(circuit, layout, freqs, solutions, x_op, circuit.temperature)


def ac_from_directive(circuit, directive):
    args = directive.args
    if len(args) < 4:
        raise CircuitError("Usage: .ac dec|oct|lin <points> <fstart> <fstop>")
    return ac_analysis(circuit, parse_value(args[2]), parse_value(args[3]), parse_value(args[1]), args[0])
