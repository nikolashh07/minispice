"""Controlled (dependent) sources: the building blocks for modeling transistors and op-amps.

  E  voltage-controlled voltage source  V(out) = gain × V(control)          (an amplifier)
  G  voltage-controlled current source  I(out) = gm × V(control)            (a transistor's gm)
  F  current-controlled current source  I(out) = gain × I(through a part)   (a BJT's beta)
  H  current-controlled voltage source  V(out) = r × I(through a part)      (a transimpedance amp)

Each one is linear, so it stamps fixed numbers into the matrix, but those numbers link one part
of the circuit to another instead of sitting symmetrically around a single part like a resistor's.
"""

from ..units import format_eng
from .base import Component, ParseError, number, reject_leftovers, split_args


def _parse_voltage_controlled(cls, name, tokens, usage):
    positional, keywords = split_args(tokens)
    if len(positional) < 5:
        raise ParseError(f"{name}: Usage: {usage}")
    nodes = positional[:4]
    gain = number(positional[4], f"{name} gain")
    reject_leftovers(name, positional[5:], keywords, usage)
    return cls(name, *nodes, gain)


def _parse_current_controlled(cls, name, tokens, usage):
    positional, keywords = split_args(tokens)
    if len(positional) < 4:
        raise ParseError(f"{name}: Usage: {usage}")
    n1, n2, control = positional[:3]
    gain = number(positional[3], f"{name} gain")
    reject_leftovers(name, positional[4:], keywords, usage)
    return cls(name, n1, n2, control, gain)


class VCVS(Component):
    letter = "E"
    kind = "VCVS"
    terminals = ("+", "-", "c+", "c-")
    n_branches = 1
    USAGE = "E<name> <out+> <out-> <control+> <control-> <gain>"

    def __init__(self, name, n1, n2, c1, c2, gain):
        super().__init__(name, [n1, n2, c1, c2])
        self.value = gain

    @classmethod
    def parse(cls, name, tokens, models):
        return _parse_voltage_controlled(cls, name, tokens, cls.USAGE)

    def dc_paths(self):
        return [(self.nodes[0], self.nodes[1])]

    def voltage_pairs(self, mode):
        return [(self.nodes[0], self.nodes[1])]

    def _stamp(self, system):
        a, b, c, d = self.idx
        system.add(a, self.br, 1.0)
        system.add(b, self.br, -1.0)
        # Branch row: V(a) - V(b) - gain (V(c) - V(d)) = 0
        system.add(self.br, a, 1.0)
        system.add(self.br, b, -1.0)
        system.add(self.br, c, -self.value)
        system.add(self.br, d, self.value)

    def stamp(self, system, ctx):
        self._stamp(system)
        if ctx.explaining:
            n = self.nodes
            ctx.note("Dependent source", f"{self.name} forces V({n[0]}) - V({n[1]}) = {self.value:g} × (V({n[2]}) - V({n[3]})).", [self.name])

    def stamp_ac(self, system, ctx):
        self._stamp(system)

    def terminal_currents(self, x, ctx):
        return [x[self.br], -x[self.br], 0.0, 0.0]

    def netlist_line(self):
        return f"{self.name} {' '.join(self.nodes)} {self.value:g}"


class VCCS(Component):
    letter = "G"
    kind = "VCCS"
    unit = "S"
    terminals = ("+", "-", "c+", "c-")
    USAGE = "G<name> <out+> <out-> <control+> <control-> <transconductance in siemens>"

    def __init__(self, name, n1, n2, c1, c2, gm):
        super().__init__(name, [n1, n2, c1, c2])
        self.value = gm

    @classmethod
    def parse(cls, name, tokens, models):
        return _parse_voltage_controlled(cls, name, tokens, cls.USAGE)

    def _stamp(self, system):
        a, b, c, d = self.idx
        gm = self.value
        # gm × V(control) leaves node a, flows through the source, and enters node b.
        system.add(a, c, gm)
        system.add(a, d, -gm)
        system.add(b, c, -gm)
        system.add(b, d, gm)

    def stamp(self, system, ctx):
        self._stamp(system)
        if ctx.explaining:
            n = self.nodes
            ctx.note("Dependent source", f"{self.name} pushes {format_eng(self.value, 'S')} × (V({n[2]}) - V({n[3]})) from node {n[0]} to node {n[1]}.", [self.name])

    def stamp_ac(self, system, ctx):
        self._stamp(system)

    def terminal_currents(self, x, ctx):
        i = self.value * self.voltage(x, 2, 3)
        return [i, -i, 0.0, 0.0]

    def netlist_line(self):
        return f"{self.name} {' '.join(self.nodes)} {self.value:g}"


class _CurrentControlled(Component):
    terminals = ("+", "-")

    def __init__(self, name, n1, n2, control, gain):
        super().__init__(name, [n1, n2])
        self.control = control
        self.value = gain

    @classmethod
    def parse(cls, name, tokens, models):
        return _parse_current_controlled(cls, name, tokens, cls.USAGE)

    def check_references(self, circuit):
        if not circuit.has(self.control):
            raise ParseError(f"{self.name} is controlled by the current through '{self.control}', but there is no part with that name")
        if not circuit.get(self.control).n_branches:
            raise ParseError(
                f"{self.name} is controlled by the current through '{self.control}', but MiniSpice only tracks the current of "
                "voltage sources, inductors and other branch parts. Add a 0 V source in series to measure the current."
            )

    def rename_references(self, rename):
        self.control = rename(self.control)

    def bind(self, layout):
        super().bind(layout)
        self.control_br = layout.branch_index[self.control.lower()]

    def netlist_line(self):
        return f"{self.name} {self.nodes[0]} {self.nodes[1]} {self.control} {self.value:g}"


class CCCS(_CurrentControlled):
    letter = "F"
    kind = "CCCS"
    USAGE = "F<name> <out+> <out-> <controlling voltage source> <current gain>"

    def _stamp(self, system):
        a, b = self.idx
        system.add(a, self.control_br, self.value)
        system.add(b, self.control_br, -self.value)

    def stamp(self, system, ctx):
        self._stamp(system)
        if ctx.explaining:
            ctx.note("Dependent source", f"{self.name} pushes {self.value:g} × I({self.control}) from node {self.nodes[0]} to node {self.nodes[1]}.", [self.name, self.control])

    def stamp_ac(self, system, ctx):
        self._stamp(system)

    def terminal_currents(self, x, ctx):
        i = self.value * x[self.control_br]
        return [i, -i]


class CCVS(_CurrentControlled):
    letter = "H"
    kind = "CCVS"
    n_branches = 1
    USAGE = "H<name> <out+> <out-> <controlling voltage source> <transresistance in ohms>"

    def dc_paths(self):
        return [tuple(self.nodes)]

    def voltage_pairs(self, mode):
        return [tuple(self.nodes)]

    def _stamp(self, system):
        a, b = self.idx
        system.add(a, self.br, 1.0)
        system.add(b, self.br, -1.0)
        system.add(self.br, a, 1.0)
        system.add(self.br, b, -1.0)
        system.add(self.br, self.control_br, -self.value)

    def stamp(self, system, ctx):
        self._stamp(system)
        if ctx.explaining:
            ctx.note("Dependent source", f"{self.name} forces V({self.nodes[0]}) - V({self.nodes[1]}) = {format_eng(self.value, 'Ω')} × I({self.control}).", [self.name, self.control])

    def stamp_ac(self, system, ctx):
        self._stamp(system)

    def terminal_currents(self, x, ctx):
        return [x[self.br], -x[self.br]]
