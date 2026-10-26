"""Bipolar junction transistor, Ebers-Moll (transport) model.

Two back-to-back junctions share a thin base. Electrons injected across the base-emitter junction
mostly sweep across the base to the collector (the transport current), and a small fraction
recombine in the base (the base current, about 1/beta of it):

    If = IS (e^(Vbe/Vt) - 1)     forward junction
    Ir = IS (e^(Vbc/Vt) - 1)     reverse junction
    Ic = (If - Ir)(1 - Vbc/VAF) - Ir/BR
    Ib = If/BF + Ir/BR

PNP transistors are the same with every voltage and current flipped.
"""

import math

from ..context import Q_ELECTRON, thermal_voltage
from ..units import format_eng
from .base import Component, ParseError, node_voltage, split_args, stamp_linearized, stamp_small_signal
from .junction import limited_voltage, safe_exp, saturation_current
from .models import find_model, is_model_name

USAGE = "Q<name> <collector> <base> <emitter> [substrate] <model>"

ON_VOLTAGE = 0.5  # a junction above this is considered forward biased when naming the region


class BJT(Component):
    letter = "Q"
    kind = "BJT"
    terminals = ("c", "b", "e")
    nonlinear = True
    MODEL_PARAMS = {"is", "bf", "br", "nf", "nr", "vaf", "eg", "xti"}

    def __init__(self, name, c, b, e, model):
        super().__init__(name, [c, b, e])
        self.model = model
        p = model.params
        self.polarity = 1 if model.type == "npn" else -1
        self.i_s = p.get("is", 1e-14)
        self.value = p.get("bf", 100.0)
        self.beta_r = p.get("br", 1.0)
        self.nf = p.get("nf", 1.0)
        self.nr = p.get("nr", 1.0)
        self.vaf = p.get("vaf", math.inf) or math.inf
        self.eg = p.get("eg", 1.11)
        self.xti = p.get("xti", 3.0)
        self.kind = model.type.upper()

    @property
    def beta_f(self):
        # The forward beta is the BJT's main value, so sweeps and Monte Carlo vary it.
        return self.value

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        keywords.pop("area", None)  # accepted for SPICE compatibility, but not used
        if keywords:
            raise ParseError(f"{name}: unknown option(s) {', '.join(k + '=' for k in keywords)}. Usage: {USAGE}")
        if len(positional) == 5 and is_model_name(models, positional[4], ("npn", "pnp")):
            positional = positional[:3] + positional[4:]  # drop the substrate node
        if len(positional) != 4:
            raise ParseError(f"{name}: Usage: {USAGE}")
        c, b, e, model = positional
        return cls(name, c, b, e, find_model(models, model, ("npn", "pnp"), name))

    def dc_paths(self):
        c, b, e = self.nodes
        return [(c, b), (b, e)]

    def _saturation(self, celsius):
        return saturation_current(self.i_s, celsius, 1.0, self.eg, self.xti)

    def evaluate(self, vbe, vbc, celsius, gmin):
        """Terminal currents (c, b, e) of an NPN and their derivatives with respect to (vbe, vbc)."""
        vt = thermal_voltage(celsius)
        i_s = self._saturation(celsius)
        ef, def_ = safe_exp(vbe / (self.nf * vt))
        er, der = safe_exp(vbc / (self.nr * vt))
        i_f = i_s * (ef - 1) + gmin * vbe
        g_f = i_s * def_ / (self.nf * vt) + gmin
        i_r = i_s * (er - 1) + gmin * vbc
        g_r = i_s * der / (self.nr * vt) + gmin
        early = 1 - vbc / self.vaf if math.isfinite(self.vaf) else 1.0
        d_early = -1 / self.vaf if math.isfinite(self.vaf) else 0.0

        ic = (i_f - i_r) * early - i_r / self.beta_r
        ib = i_f / self.beta_f + i_r / self.beta_r
        dic = [g_f * early, -g_r * early + (i_f - i_r) * d_early - g_r / self.beta_r]
        dib = [g_f / self.beta_f, g_r / self.beta_r]
        die = [-(dic[0] + dib[0]), -(dic[1] + dib[1])]
        return [ic, ib, -(ic + ib)], [dic, dib, die]

    def _junctions(self, x):
        c, b, e = (node_voltage(x, i) for i in self.idx)
        return self.polarity * (b - e), self.polarity * (b - c)

    def stamp(self, system, ctx):
        vbe, vbc = self._junctions(ctx.x)
        vt = thermal_voltage(ctx.temperature)
        i_s = self._saturation(ctx.temperature)
        vbe = limited_voltage(ctx, self.key + "#be", vbe, self.nf * vt, i_s)
        vbc = limited_voltage(ctx, self.key + "#bc", vbc, self.nr * vt, i_s)
        currents, jac = self.evaluate(vbe, vbc, ctx.temperature, ctx.gmin)
        p = self.polarity
        # Controls are the raw node differences V(b)-V(e) and V(b)-V(c). For a PNP both the
        # voltages and the currents flip sign, so the derivatives stay the same.
        stamp_linearized(system, self.idx, [p * i for i in currents], jac, [(1, 2), (1, 0)], [p * vbe, p * vbc])
        if ctx.explaining:
            ctx.note("Ebers-Moll model", f"{self.name} ({self.kind}) at Vbe = {format_eng(vbe, 'V')}: Ic = {format_eng(currents[0], 'A')}, "
                     f"Ib = {format_eng(currents[1], 'A')}.", [self.name])

    def stamp_ac(self, system, ctx):
        vbe, vbc = self._junctions(ctx.x_op)
        _, jac = self.evaluate(vbe, vbc, ctx.temperature, ctx.gmin)
        stamp_small_signal(system, self.idx, jac, [(1, 2), (1, 0)])

    def terminal_currents(self, x, ctx):
        vbe, vbc = self._junctions(x)
        currents, _ = self.evaluate(vbe, vbc, ctx.temperature, ctx.gmin)
        return [self.polarity * i for i in currents]

    def ac_terminal_currents(self, x, ctx):
        _, jac = self.evaluate(*self._junctions(ctx.x_op), ctx.temperature, ctx.gmin)
        c, b, e = (node_voltage(x, i) for i in self.idx)
        return [row[0] * (b - e) + row[1] * (b - c) for row in jac]

    def region(self, x, ctx):
        vbe, vbc = self._junctions(x)
        be_on, bc_on = vbe > ON_VOLTAGE, vbc > ON_VOLTAGE - 0.1
        if be_on and bc_on:
            return "saturation"
        if be_on:
            return "active"
        if bc_on:
            return "reverse active"
        return "cutoff"

    def noise_sources(self, x, ctx):
        ic, ib, _ = self.terminal_currents(x, ctx)
        c, b, e = self.idx
        return [(c, e, 2 * Q_ELECTRON * abs(ic)), (b, e, 2 * Q_ELECTRON * abs(ib))]

    def netlist_line(self):
        return f"{self.name} {' '.join(self.nodes)} {self.model.name}"

    def describe(self):
        return f"{self.kind} transistor {self.name} (model {self.model.name}, beta {self.beta_f:g})"
