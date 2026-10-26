"""Independent voltage and current sources: DC value, optional AC phasor, optional time waveform."""

import cmath
import math

from ..units import format_eng, is_number, parse_value
from .base import Component, ParseError, need_nodes, split_args
from .waveforms import WAVEFORM_NAMES, WAVEFORMS

SOURCE_SPEC = "[DC] <value> [AC <magnitude> [<phase°>]] [PULSE(...) | SIN(...) | PWL(...) | EXP(...) | STEP(...)]"


def parse_source_spec(name, tokens):
    """Read the part of a source line after its nodes. 'DC' is optional: 'V1 1 0 10' works."""
    dc = None
    ac = 0j
    waveform = None
    i = 0
    tokens = [t.lower() for t in tokens]

    def numbers_from(start):
        values = []
        j = start
        while j < len(tokens) and is_number(tokens[j]):
            values.append(parse_value(tokens[j]))
            j += 1
        return values, j

    while i < len(tokens):
        token = tokens[i]
        if token == "dc":
            values, _ = numbers_from(i + 1)
            if not values:
                raise ParseError(f"{name}: DC must be followed by a value, like 'DC 5'")
            dc = values[0]
            i += 2
        elif token == "ac":
            values, _ = numbers_from(i + 1)
            if not values:
                raise ParseError(f"{name}: AC must be followed by a magnitude, like 'AC 1'")
            magnitude = values[0]
            phase = values[1] if len(values) > 1 else 0.0
            ac = cmath.rect(magnitude, math.radians(phase))
            i += 1 + min(len(values), 2)
        elif token in WAVEFORM_NAMES:
            values, i = numbers_from(i + 1)
            waveform = WAVEFORMS[token](values)
        elif is_number(token) and dc is None and i == 0:
            dc = parse_value(token)
            i += 1
        else:
            raise ParseError(f"{name}: did not understand '{token}'. Usage: {name} <node+> <node-> {SOURCE_SPEC}")
    if dc is None:
        # With only a waveform, the DC operating point uses the waveform's value at t = 0, as SPICE does.
        dc = waveform.value(0.0) if waveform else 0.0
    return dc, ac, waveform


class _Source(Component):
    is_source = True

    def __init__(self, name, n1, n2, dc=0.0, ac=0j, waveform=None):
        super().__init__(name, [n1, n2])
        self.value = dc
        self.ac = ac
        self.waveform = waveform

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        if keywords:
            raise ParseError(f"{name}: sources don't take key=value options. Usage: {name} <node+> <node-> {SOURCE_SPEC}")
        n1, n2 = need_nodes(name, positional, 2, f"{name} <node+> <node-> {SOURCE_SPEC}")
        dc, ac, waveform = parse_source_spec(name, positional)
        return cls(name, n1, n2, dc, ac, waveform)

    def level(self, ctx):
        """The source's value right now: the waveform during transient, the DC value otherwise."""
        if ctx.mode == "tran" and self.waveform is not None:
            value = self.waveform.value(ctx.time)
        else:
            value = self.value
        return value * ctx.source_factor(self)

    def breakpoints(self, t_stop):
        return self.waveform.breakpoints(t_stop) if self.waveform else []

    def netlist_line(self):
        text = f"{self.name} {self.nodes[0]} {self.nodes[1]} DC {self.value:g}"
        if self.ac:
            text += f" AC {abs(self.ac):g} {math.degrees(cmath.phase(self.ac)):g}"
        if self.waveform:
            text += " " + self.waveform.spec()
        return text

    def describe(self):
        text = f"{self.kind} {self.name} ({format_eng(self.value, self.unit)})"
        if self.waveform:
            text += f" with {self.waveform.spec()}"
        return text


class VoltageSource(_Source):
    """Fixes V(node+) - V(node-). Its current is unknown, so it adds one branch row to the matrix."""

    letter = "V"
    kind = "voltage source"
    unit = "V"
    n_branches = 1

    def dc_paths(self):
        return [tuple(self.nodes)]

    def voltage_pairs(self, mode):
        return [tuple(self.nodes)]

    def _stamp_incidence(self, system):
        a, b = self.idx
        # KCL: the branch current leaves node+ into the source and comes out at node-.
        system.add(a, self.br, 1.0)
        system.add(b, self.br, -1.0)
        # Branch row (KVL): V(node+) - V(node-) = source value.
        system.add(self.br, a, 1.0)
        system.add(self.br, b, -1.0)

    def stamp(self, system, ctx):
        self._stamp_incidence(system)
        value = self.level(ctx)
        system.add_b(self.br, value)
        if ctx.explaining:
            n1, n2 = self.nodes
            ctx.note(
                "KVL",
                f"{self.name} forces V{n1} - V{n2} = {format_eng(value, 'V')}. Its current is unknown, so MNA adds "
                f"I({self.name}) as an extra unknown and this equation as an extra row.",
                [self.name],
            )

    def stamp_ac(self, system, ctx):
        self._stamp_incidence(system)
        system.add_b(self.br, self.ac * (0.0 if ctx.sources_on is not None and self.key not in ctx.sources_on else 1.0))

    def terminal_currents(self, x, ctx):
        return [x[self.br], -x[self.br]]


class CurrentSource(_Source):
    """Pushes a fixed current from node+ through itself to node- (SPICE direction)."""

    letter = "I"
    kind = "current source"
    unit = "A"

    def stamp(self, system, ctx):
        a, b = self.idx
        value = self.level(ctx)
        system.current_source(a, b, value)
        if ctx.explaining:
            n1, n2 = self.nodes
            ctx.note(
                "KCL",
                f"{self.name} takes {format_eng(value, 'A')} out of node {n1} and delivers it into node {n2}, "
                "so it only appears on the right-hand side of those KCL equations.",
                [self.name],
            )

    def stamp_ac(self, system, ctx):
        a, b = self.idx
        on = 0.0 if ctx.sources_on is not None and self.key not in ctx.sources_on else 1.0
        system.current_source(a, b, self.ac * on)

    def terminal_currents(self, x, ctx):
        value = self.level(ctx)
        return [value, -value]

    def ac_terminal_currents(self, x, ctx):
        return [self.ac, -self.ac]
