"""Time-controlled switch: closed from ton until toff, open the rest of the time.

A closed switch is a small resistance and an open one a huge resistance, rather than an ideal
short and open, so the matrix never becomes singular when the switch disconnects part of the circuit.
"""

import math

from ..units import format_eng
from .base import Component, ParseError, need_nodes, reject_leftovers, split_args, take_keyword

USAGE = "S<name> <node+> <node-> [ton=<s>] [toff=<s>] [ron=<Ω>] [roff=<Ω>]  (closed while ton <= t < toff)"


class TimeSwitch(Component):
    letter = "S"
    kind = "switch"
    unit = "Ω"

    def __init__(self, name, n1, n2, ton=0.0, toff=math.inf, ron=1e-3, roff=1e9):
        super().__init__(name, [n1, n2])
        if ron <= 0 or roff <= 0:
            raise ParseError(f"{name}: ron and roff must be positive")
        self.ton, self.toff, self.ron, self.roff = ton, toff, ron, roff

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        n1, n2 = need_nodes(name, positional, 2, USAGE)
        if positional:
            raise ParseError(
                f"{name}: MiniSpice switches are controlled by time, not by a voltage and a model. Usage: {USAGE}"
            )
        comp = cls(
            name, n1, n2,
            ton=take_keyword(keywords, "ton", "ton", 0.0),
            toff=take_keyword(keywords, "toff", "toff", math.inf),
            ron=take_keyword(keywords, "ron", "ron", 1e-3),
            roff=take_keyword(keywords, "roff", "roff", 1e9),
        )
        reject_leftovers(name, positional, keywords, USAGE)
        return comp

    def is_closed(self, t):
        return self.ton <= t < self.toff

    def resistance(self, ctx):
        t = ctx.time if ctx.mode == "tran" else 0.0
        return self.ron if self.is_closed(t) else self.roff

    def dc_paths(self):
        return [tuple(self.nodes)]

    def stamp(self, system, ctx):
        r = self.resistance(ctx)
        system.conductance(self.idx[0], self.idx[1], 1.0 / r)
        if ctx.explaining:
            state = "closed" if r == self.ron else "open"
            ctx.note("Ohm's law", f"{self.name} is {state}, so it acts as {format_eng(r, 'Ω')}.", [self.name])

    def stamp_ac(self, system, ctx):
        system.conductance(self.idx[0], self.idx[1], 1.0 / self.resistance(ctx))

    def terminal_currents(self, x, ctx):
        i = self.voltage(x) / self.resistance(ctx)
        return [i, -i]

    def breakpoints(self, t_stop):
        return [t for t in (self.ton, self.toff) if 0 < t < t_stop]

    def netlist_line(self):
        parts = [f"{self.name} {self.nodes[0]} {self.nodes[1]} ton={self.ton:g}"]
        if math.isfinite(self.toff):
            parts.append(f"toff={self.toff:g}")
        parts.append(f"ron={self.ron:g} roff={self.roff:g}")
        return " ".join(parts)

    def describe(self):
        return f"switch {self.name} (closed from {format_eng(self.ton, 's')} to {format_eng(self.toff, 's')})"
