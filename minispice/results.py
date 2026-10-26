"""Solution objects and probe expressions like v(out), v(a,b), i(R1) and p(R1)."""

import re

import numpy as np

from .components.base import node_voltage
from .errors import CircuitError

_PROBE = re.compile(r"^\s*(v|i|p|vdb|vp|vm|vr|vi|im|ip|idb)\s*\(\s*([^,)\s]+)\s*(?:,\s*([^)\s]+)\s*)?\)\s*$", re.I)


def parse_probe(expr):
    """'v(out)' -> ('v', 'out', '0'); 'i(R1)' -> ('i', 'r1', None); a bare node name means its voltage."""
    match = _PROBE.match(expr)
    if not match:
        if re.fullmatch(r"[\w.#]+", expr.strip()):
            return "v", expr.strip().lower(), "0"
        raise CircuitError(f"can't read '{expr}'. Use v(node), v(node1,node2), i(part), p(part), or vdb(node) for AC")
    kind, first, second = match.groups()
    kind = kind.lower()
    if kind.startswith("v"):
        from .netlist import normalize_node

        return kind, normalize_node(first), normalize_node(second) if second else "0"
    return kind, first.lower(), second.lower() if second else None


class Solution:
    """A DC operating point: every node voltage and branch current, plus helpers to read them."""

    def __init__(self, circuit, layout, x, ctx, iterations=1):
        self.circuit = circuit
        self.layout = layout
        self.x = x
        self.ctx = ctx
        self.iterations = iterations

    def v(self, node, ref="0"):
        return self._node(node) - self._node(ref)

    def _node(self, node):
        from .netlist import normalize_node

        node = normalize_node(str(node))
        if node == "0":
            return 0.0
        if node not in self.layout.node_index:
            raise CircuitError(f"There is no node '{node}'. Nodes: {', '.join(self.layout.nodes)}")
        return float(self.x[self.layout.node_index[node]])

    def i(self, name, terminal=None):
        """Current into a part's terminal (the first terminal by default), passive sign convention."""
        comp = self.circuit.get(name)
        currents = comp.terminal_currents(self.x, self.ctx)
        return float(currents[_terminal_number(comp, terminal)])

    def p(self, name):
        """Power absorbed by a part. Negative means it delivers power."""
        return float(self.circuit.get(name).power(self.x, self.ctx))

    def region(self, name):
        return self.circuit.get(name).region(self.x, self.ctx)

    @property
    def node_voltages(self):
        return {node: float(self.x[i]) for node, i in self.layout.node_index.items() if "#" not in node}

    def measure(self, expr):
        kind, first, second = parse_probe(expr)
        if kind == "v":
            return self.v(first, second)
        if kind == "i":
            return self.i(first, second)
        if kind == "p":
            return self.p(first)
        raise CircuitError(f"'{expr}' only makes sense for AC analysis")

    def component_rows(self):
        """(name, kind, voltage across, current in, power absorbed, region) for every part."""
        rows = []
        for comp in self.circuit.components:
            currents = comp.terminal_currents(self.x, self.ctx)
            rows.append((
                comp.name,
                comp.kind,
                comp.voltage(self.x),
                float(currents[0]),
                float(comp.power(self.x, self.ctx)),
                comp.region(self.x, self.ctx),
            ))
        return rows

    def __getitem__(self, expr):
        return self.measure(expr)


def _terminal_number(comp, terminal):
    if terminal is None:
        return 0
    if isinstance(terminal, int):
        return terminal
    names = [t.lower() for t in comp.terminals]
    if terminal.lower() not in names:
        raise CircuitError(f"{comp.name} has terminals {', '.join(comp.terminals)}, not '{terminal}'")
    return names.index(terminal.lower())


def node_voltage_array(x, idx):
    return np.array([node_voltage(x, i) for i in idx])
