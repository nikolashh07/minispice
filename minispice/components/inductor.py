"""Inductor: v = L di/dt (Faraday's law; the minus sign of Lenz's law is why it opposes changes in current).

Its current is a matrix unknown (a branch), which makes the inductor easy to write at DC
(a short circuit: v = 0), in transient (a companion model) and in AC (impedance jωL).
"""

from ..units import format_eng
from .base import Component, ParseError, need_nodes, number, reject_leftovers, split_args, take_keyword, take_tolerance

USAGE = "L<name> <node+> <node-> <henries> [ic=<initial amps>] [tol=10%]"


class Inductor(Component):
    letter = "L"
    kind = "inductor"
    unit = "H"
    dynamic = True
    n_branches = 1

    def __init__(self, name, n1, n2, inductance, ic=None):
        super().__init__(name, [n1, n2])
        if inductance <= 0:
            raise ParseError(f"{name}: inductance must be positive")
        self.value = inductance
        self.ic = ic

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        n1, n2 = need_nodes(name, positional, 2, USAGE)
        if not positional:
            raise ParseError(f"{name} has no inductance. Usage: {USAGE}")
        comp = cls(name, n1, n2, number(positional.pop(0), f"{name} inductance"), take_keyword(keywords, "ic", "initial current"))
        take_tolerance(comp, keywords)
        reject_leftovers(name, positional, keywords, USAGE)
        return comp

    def dc_paths(self):
        return [tuple(self.nodes)]

    def voltage_pairs(self, mode):
        return [tuple(self.nodes)] if mode == "dc" else []

    def _incidence(self, system):
        a, b = self.idx
        system.add(a, self.br, 1.0)
        system.add(b, self.br, -1.0)
        system.add(self.br, a, 1.0)
        system.add(self.br, b, -1.0)

    def history_factor(self, ctx):
        """L/h for backward Euler, 2L/h for trapezoidal (the 'resistance' of the companion model)."""
        return (1.0 if ctx.method == "be" else 2.0) * self.value / ctx.h

    def stamp(self, system, ctx):
        self._incidence(system)
        if ctx.mode != "tran":
            # Branch row: V(a) - V(b) = 0. At DC an inductor is a short circuit.
            if ctx.explaining:
                ctx.note("Faraday's law", f"At DC the current doesn't change, so v = L di/dt = 0 and {self.name} is a short circuit.", [self.name])
            return
        # Backward Euler: v_n - (L/h) i_n = -(L/h) i_prev
        # Trapezoidal:    v_n - (2L/h) i_n = -(2L/h) i_prev - v_prev
        v_prev, i_prev = ctx.state[self.key]
        r = self.history_factor(ctx)
        system.add(self.br, self.br, -r)
        rhs = -r * i_prev
        if ctx.method != "be":
            rhs -= v_prev
        system.add_b(self.br, rhs)

    def stamp_ac(self, system, ctx):
        self._incidence(system)
        system.add(self.br, self.br, -1j * ctx.omega * self.value)

    def terminal_currents(self, x, ctx):
        return [x[self.br], -x[self.br]]

    def initial_state(self, x, ctx):
        i = self.ic if (ctx.uic and self.ic is not None) else (0.0 if ctx.uic else x[self.br])
        return (self.voltage(x), i)

    def update_state(self, x, ctx):
        return (self.voltage(x), x[self.br])

    def energy(self, i):
        return 0.5 * self.value * i * i

    def netlist_line(self):
        extra = f" ic={self.ic:g}" if self.ic is not None else ""
        if self.tol:
            extra += f" tol={self.tol * 100:g}%"
        return f"{self.name} {self.nodes[0]} {self.nodes[1]} {self.value:g}{extra}"

    def describe(self):
        return f"inductor {self.name} ({format_eng(self.value, 'H')})"
