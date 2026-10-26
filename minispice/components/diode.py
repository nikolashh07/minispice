"""Diode: the Shockley equation I = IS (e^(V / N·Vt) - 1).

Nonlinear, so it is solved with Newton's method: at each guess the diode is replaced by its
tangent line, a conductance g = dI/dV in parallel with a current source. Zener diodes add a
reverse breakdown current at -BV, and LEDs are diodes whose parameters put the turn-on near 2 V.
"""

import math

from ..context import K_BOLTZMANN, Q_ELECTRON, kelvin, thermal_voltage
from ..units import format_eng
from .base import Component, ParseError, node_voltage, number, split_args, stamp_linearized, stamp_small_signal
from .junction import limited_voltage, safe_exp, saturation_current
from .models import find_model

USAGE = "D<name> <anode> <cathode> [model] [area=<factor>]"


class Diode(Component):
    letter = "D"
    kind = "diode"
    terminals = ("a", "k")
    nonlinear = True
    MODEL_PARAMS = {"is", "n", "rs", "bv", "ibv", "eg", "xti"}

    def __init__(self, name, anode, cathode, model, area=1.0):
        super().__init__(name, [anode, cathode])
        self.model = model
        p = model.params
        self.i_s = p.get("is", 1e-14) * area
        self.n = p.get("n", 1.0)
        self.rs = p.get("rs", 0.0) / area
        self.bv = p.get("bv", math.inf)
        self.ibv = p.get("ibv", 1e-3)
        self.eg = p.get("eg", 1.11)
        self.xti = p.get("xti", 3.0)

    # The saturation current is the diode's main value, so sweeps and Monte Carlo vary it.
    @property
    def value(self):
        return getattr(self, "i_s", None)

    @value.setter
    def value(self, i_s):
        if i_s is not None:
            self.i_s = i_s

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        if len(positional) < 2:
            raise ParseError(f"{name} needs two nodes. Usage: {USAGE}")
        anode, cathode = positional[:2]
        model_name = positional[2] if len(positional) > 2 else "d"
        if len(positional) > 3:
            raise ParseError(f"{name}: unexpected '{' '.join(positional[3:])}'. Usage: {USAGE}")
        area = number(keywords.pop("area"), f"{name} area") if "area" in keywords else 1.0
        if keywords:
            raise ParseError(f"{name}: unknown option(s) {', '.join(k + '=' for k in keywords)}. Usage: {USAGE}")
        return cls(name, anode, cathode, find_model(models, model_name, ("d",), name), area)

    def internal_nodes(self):
        # Series resistance gets its own node between the resistor and the ideal junction.
        return [f"{self.key}#a"] if self.rs > 0 else []

    def dc_paths(self):
        if self.rs > 0:
            inner = self.internal_nodes()[0]
            return [(self.nodes[0], inner), (inner, self.nodes[1])]
        return [tuple(self.nodes)]

    @property
    def _junction_nodes(self):
        """Matrix indices of the junction's two ends (after the series resistance)."""
        return (self.idx[2] if self.rs > 0 else self.idx[0], self.idx[1])

    def junction(self, vd, celsius, gmin):
        """Current and conductance of the junction at voltage vd."""
        nvt = self.n * thermal_voltage(celsius)
        i_s = saturation_current(self.i_s, celsius, self.n, self.eg, self.xti)
        e, de = safe_exp(vd / nvt)
        i = i_s * (e - 1)
        g = i_s * de / nvt
        if math.isfinite(self.bv):
            # Breakdown: a second exponential that switches on as vd approaches -BV.
            vt = thermal_voltage(celsius)
            eb, deb = safe_exp(-(vd + self.bv) / vt)
            i -= self.ibv * eb
            g += self.ibv * deb / vt
        return i + gmin * vd, g + gmin

    def _vd(self, x):
        p, n = self._junction_nodes
        return node_voltage(x, p) - node_voltage(x, n)

    def stamp(self, system, ctx):
        p, n = self._junction_nodes
        if self.rs > 0:
            system.conductance(self.idx[0], p, 1.0 / self.rs)
        nvt = self.n * thermal_voltage(ctx.temperature)
        vd = self._vd(ctx.x)
        if math.isfinite(self.bv) and vd < 0:
            # Mirror the limiting for the breakdown knee: limit -(vd + BV) the same way.
            mirrored = limited_voltage(ctx, self.key + "#bv", -(vd + self.bv), thermal_voltage(ctx.temperature), self.ibv)
            vd = -(mirrored + self.bv)
        else:
            vd = limited_voltage(ctx, self.key, vd, nvt, saturation_current(self.i_s, ctx.temperature, self.n, self.eg, self.xti))
        i, g = self.junction(vd, ctx.temperature, ctx.gmin)
        stamp_linearized(system, [p, n], [i, -i], [[g], [-g]], [(0, 1)], [vd])
        if ctx.explaining:
            ctx.note(
                "Shockley diode equation",
                f"{self.name} at {format_eng(vd, 'V')} conducts {format_eng(i, 'A')}; its tangent line there is a "
                f"{format_eng(1 / g, 'Ω')} resistor in parallel with a {format_eng(i - g * vd, 'A')} current source.",
                [self.name],
            )

    def stamp_ac(self, system, ctx):
        p, n = self._junction_nodes
        if self.rs > 0:
            system.conductance(self.idx[0], p, 1.0 / self.rs)
        _, g = self.junction(self._vd(ctx.x_op), ctx.temperature, ctx.gmin)
        stamp_small_signal(system, [p, n], [[g], [-g]], [(0, 1)])

    def terminal_currents(self, x, ctx):
        i, _ = self.junction(self._vd(x), ctx.temperature, ctx.gmin)
        return [i, -i]

    def ac_terminal_currents(self, x, ctx):
        _, g = self.junction(self._vd(ctx.x_op), ctx.temperature, ctx.gmin)
        p, n = self._junction_nodes
        i = g * (node_voltage(x, p) - node_voltage(x, n))
        return [i, -i]

    def region(self, x, ctx):
        vd = self._vd(x)
        if math.isfinite(self.bv) and vd <= -0.9 * self.bv:
            return "breakdown"
        i, _ = self.junction(vd, ctx.temperature, 0.0)
        return "on" if i > 1e-6 else "off"

    def noise_sources(self, x, ctx):
        # Shot noise: current is made of individual electrons, which arrive randomly (PSD 2qI).
        i, _ = self.junction(self._vd(x), ctx.temperature, 0.0)
        p, n = self._junction_nodes
        sources = [(p, n, 2 * Q_ELECTRON * abs(i))]
        if self.rs > 0:
            sources.append((self.idx[0], p, 4 * K_BOLTZMANN * kelvin(ctx.temperature) / self.rs))
        return sources

    def netlist_line(self):
        return f"{self.name} {self.nodes[0]} {self.nodes[1]} {self.model.name}"

    def describe(self):
        return f"diode {self.name} (model {self.model.name})"
