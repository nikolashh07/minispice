"""Resistor: Ohm's law, V = I R."""

from ..context import K_BOLTZMANN, T_NOMINAL_C, kelvin
from ..units import format_eng
from .base import Component, ParseError, need_nodes, number, reject_leftovers, split_args, take_keyword, take_tolerance

USAGE = "R<name> <node+> <node-> <ohms> [tc1=<1/°C>] [tc2=<1/°C²>] [tol=5%] [rating=<watts>]"


class Resistor(Component):
    letter = "R"
    kind = "resistor"
    unit = "Ω"

    def __init__(self, name, n1, n2, resistance, tc1=0.0, tc2=0.0, rating=None):
        super().__init__(name, [n1, n2])
        if resistance == 0:
            raise ParseError(f"{name} is 0 Ω. Use a 0 V voltage source if you want an ideal wire you can measure current through.")
        self.value = resistance
        self.tc1 = tc1
        self.tc2 = tc2
        self.rating = rating  # maximum safe power in watts

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        n1, n2 = need_nodes(name, positional, 2, USAGE)
        if not positional and "r" not in keywords:
            raise ParseError(f"{name} has no resistance. Usage: {USAGE}")
        value = number(positional.pop(0) if positional else keywords.pop("r"), f"{name} resistance")
        comp = cls(
            name, n1, n2, value,
            tc1=take_keyword(keywords, "tc1", "tc1", 0.0),
            tc2=take_keyword(keywords, "tc2", "tc2", 0.0),
            rating=take_keyword(keywords, "rating", "power rating"),
        )
        take_tolerance(comp, keywords)
        reject_leftovers(name, positional, keywords, USAGE)
        return comp

    def resistance(self, ctx):
        # Most metals get more resistive as they heat up: R(T) = R0 (1 + tc1 ΔT + tc2 ΔT²).
        dt = ctx.temperature - T_NOMINAL_C
        return self.value * (1 + self.tc1 * dt + self.tc2 * dt * dt)

    def dc_paths(self):
        return [tuple(self.nodes)]

    def stamp(self, system, ctx):
        r = self.resistance(ctx)
        g = 1.0 / r
        a, b = self.idx
        system.conductance(a, b, g)
        if ctx.explaining:
            n1, n2 = self.nodes
            ctx.note(
                "Ohm's law",
                f"{self.name} ({format_eng(r, 'Ω')}) carries current (V({n1}) - V({n2})) / {format_eng(r, 'Ω')}, "
                f"so it adds a conductance of {format_eng(g, 'S')} to the KCL equations of nodes {n1} and {n2}.",
                [self.name],
            )

    def stamp_ac(self, system, ctx):
        a, b = self.idx
        system.conductance(a, b, 1.0 / self.resistance(ctx))

    def terminal_currents(self, x, ctx):
        i = self.voltage(x) / self.resistance(ctx)
        return [i, -i]

    def noise_sources(self, x, ctx):
        # Johnson-Nyquist: thermal motion of electrons makes a noise current with PSD 4kT/R.
        return [(self.idx[0], self.idx[1], 4 * K_BOLTZMANN * kelvin(ctx.temperature) / self.resistance(ctx))]

    def netlist_line(self):
        extra = ""
        if self.tc1:
            extra += f" tc1={self.tc1:g}"
        if self.tc2:
            extra += f" tc2={self.tc2:g}"
        if self.tol:
            extra += f" tol={self.tol * 100:g}%"
        if self.rating:
            extra += f" rating={self.rating:g}"
        return f"{self.name} {self.nodes[0]} {self.nodes[1]} {self.value:g}{extra}"
