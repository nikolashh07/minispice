"""Capacitor: i = C dv/dt.

At DC nothing changes, so no current flows: a capacitor is an open circuit. In transient
analysis each time step replaces it with a "companion model", a resistor in parallel with a
current source that together reproduce i = C dv/dt over that step, so the DC solver still works.
In AC analysis it is an impedance 1/(jωC).
"""

from ..units import format_eng
from .base import Component, ParseError, need_nodes, number, reject_leftovers, split_args, take_keyword, take_tolerance

USAGE = "C<name> <node+> <node-> <farads> [ic=<initial volts>] [tol=10%]"


class Capacitor(Component):
    letter = "C"
    kind = "capacitor"
    unit = "F"
    dynamic = True

    def __init__(self, name, n1, n2, capacitance, ic=None):
        super().__init__(name, [n1, n2])
        if capacitance <= 0:
            raise ParseError(f"{name}: capacitance must be positive")
        self.value = capacitance
        self.ic = ic

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        n1, n2 = need_nodes(name, positional, 2, USAGE)
        if not positional:
            raise ParseError(f"{name} has no capacitance. Usage: {USAGE}")
        comp = cls(name, n1, n2, number(positional.pop(0), f"{name} capacitance"), take_keyword(keywords, "ic", "initial voltage"))
        take_tolerance(comp, keywords)
        reject_leftovers(name, positional, keywords, USAGE)
        return comp

    def companion(self, ctx):
        """(conductance, history current) for this time step.

        Backward Euler:  i_n = C/h (v_n - v_prev)                 -> G = C/h,  history = G v_prev
        Trapezoidal:     i_n = 2C/h (v_n - v_prev) - i_prev       -> G = 2C/h, history = G v_prev + i_prev
        """
        v_prev, i_prev = ctx.state[self.key]
        if ctx.method == "be":
            g = self.value / ctx.h
            return g, g * v_prev
        g = 2 * self.value / ctx.h
        return g, g * v_prev + i_prev

    def stamp(self, system, ctx):
        if ctx.mode != "tran":
            if ctx.explaining:
                ctx.note("Capacitor law", f"At DC nothing changes, so dv/dt = 0 and {self.name} carries no current (open circuit).", [self.name])
            return
        a, b = self.idx
        g, history = self.companion(ctx)
        system.conductance(a, b, g)
        # i = G v - history: the history part is a fixed current flowing from b to a.
        system.current_source(a, b, -history)

    def stamp_ac(self, system, ctx):
        a, b = self.idx
        system.conductance(a, b, 1j * ctx.omega * self.value)

    def terminal_currents(self, x, ctx):
        if ctx.mode != "tran":
            return [0.0, 0.0]
        _, i = ctx.state[self.key]
        return [i, -i]

    def ac_terminal_currents(self, x, ctx):
        i = 1j * ctx.omega * self.value * self.voltage(x)
        return [i, -i]

    def initial_state(self, x, ctx):
        v = self.ic if (ctx.uic and self.ic is not None) else self.voltage(x)
        return (v, 0.0)

    def update_state(self, x, ctx):
        g, history = self.companion(ctx)
        v = self.voltage(x)
        return (v, g * v - history)

    def energy(self, v):
        return 0.5 * self.value * v * v

    def netlist_line(self):
        extra = f" ic={self.ic:g}" if self.ic is not None else ""
        if self.tol:
            extra += f" tol={self.tol * 100:g}%"
        return f"{self.name} {self.nodes[0]} {self.nodes[1]} {self.value:g}{extra}"

    def describe(self):
        return f"capacitor {self.name} ({format_eng(self.value, 'F')})"
