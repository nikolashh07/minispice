"""Operational amplifier, ideal or realistic.

Ideal: infinite gain. With negative feedback the only way the output stays finite is if the two
inputs are at the same voltage, the "virtual short". MNA writes exactly that as the op-amp's
equation, V(in+) - V(in-) = 0, and lets the output current be whatever it takes.

Realistic: finite gain A, an output that can't swing past the supply rails, and a gain-bandwidth
product (one pole at GBW / A, so the gain falls 20 dB per decade above it).

    U1 in+ in- out                          ideal
    U2 in+ in- out a=100k vpos=15 vneg=-15 gbw=1meg
    U3 in+ in- out lm741                    from a model
"""

import math

from ..units import format_eng
from .base import Component, ParseError, node_voltage, number, split_args
from .models import find_model

USAGE = "U<name> <in+> <in-> <out> [model] [a=<gain>] [vpos=<V>] [vneg=<V>] [gbw=<Hz>]"


class OpAmp(Component):
    letter = "U"
    kind = "op-amp"
    terminals = ("in+", "in-", "out")
    n_branches = 1

    def __init__(self, name, inp, inn, out, gain=None, vpos=math.inf, vneg=-math.inf, gbw=None):
        super().__init__(name, [inp, inn, out])
        if gain is None and (math.isfinite(vpos) or math.isfinite(vneg) or gbw):
            gain = 1e5  # rails or bandwidth only make sense with a finite gain
        self.value = gain  # None means ideal
        self.vpos, self.vneg, self.gbw = vpos, vneg, gbw
        if vpos <= vneg:
            raise ParseError(f"{name}: vpos must be above vneg")
        # Only the clipping makes it nonlinear; finite gain alone is still a straight line.
        self.nonlinear = gain is not None and (math.isfinite(vpos) or math.isfinite(vneg))

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        if len(positional) < 3:
            raise ParseError(f"{name} needs three nodes. Usage: {USAGE}")
        nodes = positional[:3]
        params = {}
        rest = positional[3:]
        if rest:
            params.update(find_model(models, rest.pop(0), ("opamp",), name).params)
        if rest:
            raise ParseError(f"{name}: unexpected '{' '.join(rest)}'. Usage: {USAGE}")
        for key, value in keywords.items():
            if key not in ("a", "vpos", "vneg", "gbw"):
                raise ParseError(f"{name}: unknown option {key}=. Usage: {USAGE}")
            params[key] = number(value, f"{name} {key}")
        return cls(name, *nodes, gain=params.get("a"), vpos=params.get("vpos", math.inf),
                   vneg=params.get("vneg", -math.inf), gbw=params.get("gbw"))

    @property
    def ideal(self):
        return self.value is None

    def dc_paths(self):
        return [(self.nodes[2], "0")]

    # ---- the realistic model -------------------------------------------------------------------
    def transfer(self, vd):
        """Output voltage (before the bandwidth lag) and its slope, for differential input vd."""
        a = self.value
        if not self.nonlinear:
            return a * vd, a
        top = self.vpos if math.isfinite(self.vpos) else 1e6
        bottom = self.vneg if math.isfinite(self.vneg) else -1e6
        mid, half = (top + bottom) / 2, (top - bottom) / 2
        # tanh is a straight line of slope A near the middle and flattens out at the rails.
        u = (a * vd - mid) / half
        t = math.tanh(u)
        return mid + half * t, a * (1 - t * t)

    @property
    def tau(self):
        """Time constant of the single pole: the open-loop gain drops 3 dB at GBW / A."""
        if self.ideal or not self.gbw:
            return 0.0
        return self.value / (2 * math.pi * self.gbw)

    def stamp(self, system, ctx):
        inp, inn, out = self.idx
        system.add(out, self.br, 1.0)  # the branch current is what the output pin sinks
        if self.ideal:
            system.add(self.br, inp, 1.0)
            system.add(self.br, inn, -1.0)
            if ctx.explaining:
                ctx.note("Virtual short", f"{self.name} is ideal: with negative feedback its inputs sit at the same voltage, "
                         f"so V{self.nodes[0]} = V{self.nodes[1]}, and no current flows into the inputs.", [self.name])
            return
        vd = 0.0 if ctx.x is None else node_voltage(ctx.x, inp) - node_voltage(ctx.x, inn)
        f0, slope = self.transfer(vd)
        # Branch row: k V(out) - slope (V(in+) - V(in-)) = f0 - slope vd + history, where k and the
        # history come from the bandwidth lag τ dVout/dt + Vout = f(vd) (backward Euler in time).
        k, history = 1.0, 0.0
        if ctx.mode == "tran" and self.tau:
            (vo_prev,) = ctx.state[self.key]
            k = 1.0 + self.tau / ctx.h
            history = self.tau / ctx.h * vo_prev
        system.add(self.br, out, k)
        system.add(self.br, inp, -slope)
        system.add(self.br, inn, slope)
        system.add_b(self.br, f0 - slope * vd + history)
        if ctx.explaining:
            ctx.note("Op-amp model", f"{self.name}: Vout = {format_eng(self.value, '')} × (V{self.nodes[0]} - V{self.nodes[1]}), limited to the rails.", [self.name])

    def stamp_ac(self, system, ctx):
        inp, inn, out = self.idx
        system.add(out, self.br, 1.0)
        if self.ideal:
            system.add(self.br, inp, 1.0)
            system.add(self.br, inn, -1.0)
            return
        vd = 0.0
        if ctx.x_op is not None:
            vd = node_voltage(ctx.x_op, inp) - node_voltage(ctx.x_op, inn)
        _, slope = self.transfer(vd)
        # One pole: Vout (1 + jωτ) = slope × Vd
        system.add(self.br, out, 1.0 + 1j * ctx.omega * self.tau)
        system.add(self.br, inp, -slope)
        system.add(self.br, inn, slope)

    def terminal_currents(self, x, ctx):
        return [0.0, 0.0, x[self.br]]

    def initial_state(self, x, ctx):
        return (node_voltage(x, self.idx[2]),) if self.tau else None

    def update_state(self, x, ctx):
        return (node_voltage(x, self.idx[2]),) if self.tau else None

    def netlist_line(self):
        text = f"{self.name} {' '.join(self.nodes)}"
        if not self.ideal:
            text += f" a={self.value:g}"
            if math.isfinite(self.vpos):
                text += f" vpos={self.vpos:g}"
            if math.isfinite(self.vneg):
                text += f" vneg={self.vneg:g}"
            if self.gbw:
                text += f" gbw={self.gbw:g}"
        return text

    def describe(self):
        if self.ideal:
            return f"ideal op-amp {self.name}"
        return f"op-amp {self.name} (gain {self.value:g})"
