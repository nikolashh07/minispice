"""MOSFET, square-law (SPICE level 1) model.

The gate voltage pulls a thin channel of carriers under the oxide once Vgs passes the threshold Vt:

  cutoff      Vgs < Vt              no channel, no current
  linear      Vds < Vgs - Vt        the channel acts like a voltage-controlled resistor
                                    Id = k ((Vgs - Vt) Vds - Vds²/2)
  saturation  Vds ≥ Vgs - Vt        the channel pinches off at the drain end, so the current
                                    stops growing with Vds: Id = ½ k (Vgs - Vt)² (1 + λ Vds)

with k = KP × W/L. A P-channel device is the same with every voltage and current flipped.
The body terminal is accepted but the body effect is not modeled.
"""

from ..context import K_BOLTZMANN, kelvin
from ..units import format_eng
from .base import Component, ParseError, node_voltage, number, split_args, stamp_linearized, stamp_small_signal
from .models import find_model, is_model_name

USAGE = "M<name> <drain> <gate> <source> [body] <model> [w=<m>] [l=<m>]"
MAX_VGS_STEP = 1.0  # volts per Newton iteration; keeps a wild guess from overshooting the square law


class MOSFET(Component):
    letter = "M"
    kind = "MOSFET"
    terminals = ("d", "g", "s")
    nonlinear = True

    def __init__(self, name, d, g, s, model, w=1.0, l=1.0):
        super().__init__(name, [d, g, s])
        self.model = model
        p = model.params
        self.polarity = 1 if model.type == "nmos" else -1
        self.vto = p.get("vto", 1.0 if self.polarity > 0 else -1.0)
        self.kp = p.get("kp", 2e-5)
        self.lam = p.get("lambda", 0.0)
        self.w, self.l = w, l
        if l <= 0 or w <= 0:
            raise ParseError(f"{name}: w and l must be positive")
        self.kind = model.type.upper()

    @property
    def k(self):
        return self.kp * self.w / self.l

    # k is the MOSFET's main value, so sweeps and Monte Carlo vary it (through KP).
    @property
    def value(self):
        return self.k

    @value.setter
    def value(self, k):
        if k is not None:
            self.kp = k * self.l / self.w

    @property
    def vt(self):
        """Threshold as a positive number for both types (VTO is negative for PMOS)."""
        return self.polarity * self.vto

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        w = number(keywords.pop("w"), f"{name} w") if "w" in keywords else 1.0
        l = number(keywords.pop("l"), f"{name} l") if "l" in keywords else 1.0
        if keywords:
            raise ParseError(f"{name}: unknown option(s) {', '.join(k + '=' for k in keywords)}. Usage: {USAGE}")
        if len(positional) == 5:
            positional = positional[:3] + positional[4:]  # drop the body node
        elif len(positional) == 4 and not is_model_name(models, positional[3], ("nmos", "pmos")):
            raise ParseError(f"{name}: '{positional[3]}' isn't a NMOS or PMOS model. Usage: {USAGE}")
        if len(positional) != 4:
            raise ParseError(f"{name}: Usage: {USAGE}")
        d, g, s, model = positional
        return cls(name, d, g, s, find_model(models, model, ("nmos", "pmos"), name), w, l)

    def dc_paths(self):
        # The gate is insulated, so only drain-source conducts (through gmin when off).
        return [(self.nodes[0], self.nodes[2])]

    def _square_law(self, vgs, vds):
        """Drain current and (gm, gds) for vds >= 0."""
        vov = vgs - self.vt
        if vov <= 0:
            return 0.0, 0.0, 0.0
        clm = 1 + self.lam * vds
        if vds < vov:
            i0 = self.k * (vov * vds - vds * vds / 2)
            return i0 * clm, self.k * vds * clm, self.k * (vov - vds) * clm + i0 * self.lam
        i0 = 0.5 * self.k * vov * vov
        return i0 * clm, self.k * vov * clm, i0 * self.lam

    def evaluate(self, vgs, vds, gmin):
        """Drain current of an NMOS-oriented device and its derivatives (d/dvgs, d/dvds)."""
        if vds >= 0:
            i, gm, gds = self._square_law(vgs, vds)
        else:
            # The device is symmetric: with Vds < 0 the source and drain swap roles.
            i_rev, gm_rev, gds_rev = self._square_law(vgs - vds, -vds)
            i, gm, gds = -i_rev, -gm_rev, gm_rev + gds_rev
        return i + gmin * vds, gm, gds + gmin

    def _voltages(self, x):
        d, g, s = (node_voltage(x, i) for i in self.idx)
        p = self.polarity
        return p * (g - s), p * (d - s)

    def _limit(self, ctx, vgs, vds):
        """Keep one Newton step from moving Vgs or Vds absurdly far (SPICE does the same).

        When the transistor drives a node that nothing else holds, the tangent line can predict
        thousands of volts there; following it makes Newton bounce instead of converge.
        """
        old = ctx.limits.get(self.key)
        if old is not None:
            old_vgs, old_vds = old
            if abs(vgs - old_vgs) > MAX_VGS_STEP:
                vgs = old_vgs + MAX_VGS_STEP * (1 if vgs > old_vgs else -1)
                ctx.limited = True
            limited_vds = _limit_vds(vds, old_vds) if old_vds >= 0 else -_limit_vds(-vds, -old_vds)
            if limited_vds != vds:
                vds = limited_vds
                ctx.limited = True
        ctx.limits[self.key] = (vgs, vds)
        return vgs, vds

    def stamp(self, system, ctx):
        vgs, vds = self._voltages(ctx.x)
        if ctx.mode != "ac":
            vgs, vds = self._limit(ctx, vgs, vds)
        i, gm, gds = self.evaluate(vgs, vds, ctx.gmin)
        p = self.polarity
        jac = [[gm, gds], [0.0, 0.0], [-gm, -gds]]
        stamp_linearized(system, self.idx, [p * i, 0.0, -p * i], jac, [(1, 2), (0, 2)], [p * vgs, p * vds])
        if ctx.explaining:
            ctx.note("Square-law MOSFET model", f"{self.name} ({self.kind}) has Vgs = {format_eng(vgs, 'V')}, Vds = {format_eng(vds, 'V')}, "
                     f"so it is in {self._region(vgs, vds)} and carries Id = {format_eng(i, 'A')}.", [self.name])

    def stamp_ac(self, system, ctx):
        vgs, vds = self._voltages(ctx.x_op)
        _, gm, gds = self.evaluate(vgs, vds, ctx.gmin)
        stamp_small_signal(system, self.idx, [[gm, gds], [0.0, 0.0], [-gm, -gds]], [(1, 2), (0, 2)])

    def terminal_currents(self, x, ctx):
        vgs, vds = self._voltages(x)
        i, _, _ = self.evaluate(vgs, vds, ctx.gmin)
        return [self.polarity * i, 0.0, -self.polarity * i]

    def ac_terminal_currents(self, x, ctx):
        _, gm, gds = self.evaluate(*self._voltages(ctx.x_op), ctx.gmin)
        d, g, s = (node_voltage(x, i) for i in self.idx)
        i = gm * (g - s) + gds * (d - s)
        return [i, 0.0, -i]

    def _region(self, vgs, vds):
        if vgs <= self.vt:
            return "cutoff"
        return "linear" if abs(vds) < vgs - self.vt else "saturation"

    def region(self, x, ctx):
        return self._region(*self._voltages(x))

    def noise_sources(self, x, ctx):
        # Channel thermal noise, 8kT·gm/3 in saturation (the textbook long-channel result).
        vgs, vds = self._voltages(x)
        _, gm, _ = self.evaluate(vgs, vds, 0.0)
        return [(self.idx[0], self.idx[2], 8 * K_BOLTZMANN * kelvin(ctx.temperature) * gm / 3)]

    def netlist_line(self):
        size = f" w={self.w:g} l={self.l:g}" if (self.w, self.l) != (1.0, 1.0) else ""
        return f"{self.name} {' '.join(self.nodes)} {self.model.name}{size}"

    def describe(self):
        return f"{self.kind} transistor {self.name} (k = {format_eng(self.k, 'A/V²')}, Vt = {self.vt:g} V)"


def _limit_vds(new, old):
    """SPICE's drain-source limiting rule: big jumps are allowed only in steps."""
    if old >= 3.5:
        if new > old:
            return min(new, 3 * old + 2)
        if new < 3.5:
            return max(new, 2.0)
        return new
    if new > old:
        return min(new, 4.0)
    return max(new, -0.5)
