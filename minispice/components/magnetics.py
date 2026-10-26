"""Coupled inductors (K) and the ideal transformer (T).

Mutual inductance: when two coils share magnetic flux, a changing current in one induces a
voltage in the other (Faraday's law): v1 = L1 di1/dt + M di2/dt, with M = k √(L1 L2).
In the matrix this is just an extra entry linking each inductor's branch row to the other's current.
"""

import math

from .base import Component, ParseError, number, reject_leftovers, split_args
from .inductor import Inductor

K_USAGE = "K<name> <inductor 1> <inductor 2> <coupling factor 0..1>"
T_USAGE = "T<name> <primary+> <primary-> <secondary+> <secondary-> <turns ratio Np/Ns>"


class MutualInductance(Component):
    letter = "K"
    kind = "coupling"
    terminals = ()

    def __init__(self, name, l1, l2, k):
        super().__init__(name, [])
        if not 0 < k <= 1:
            raise ParseError(f"{name}: coupling factor k must be between 0 and 1, got {k:g}")
        self.l1_name, self.l2_name = l1, l2
        self.value = k

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        if len(positional) < 3:
            raise ParseError(f"{name}: Usage: {K_USAGE}")
        l1, l2, k = positional[0], positional[1], number(positional[2], f"{name} coupling factor")
        reject_leftovers(name, positional[3:], keywords, K_USAGE)
        return cls(name, l1, l2, k)

    def check_references(self, circuit):
        for ref in (self.l1_name, self.l2_name):
            if not circuit.has(ref):
                raise ParseError(f"{self.name} couples '{ref}', but there is no part with that name")
            if not isinstance(circuit.get(ref), Inductor):
                raise ParseError(f"{self.name} couples '{ref}', which is not an inductor")
        if self.l1_name.lower() == self.l2_name.lower():
            raise ParseError(f"{self.name} couples {self.l1_name} to itself")

    def rename_references(self, rename):
        self.l1_name, self.l2_name = rename(self.l1_name), rename(self.l2_name)

    def bind(self, layout):
        super().bind(layout)
        self.l1 = layout.circuit.get(self.l1_name)
        self.l2 = layout.circuit.get(self.l2_name)

    @property
    def mutual(self):
        return self.value * math.sqrt(self.l1.value * self.l2.value)

    def stamp(self, system, ctx):
        if ctx.mode != "tran":
            return  # at DC no current changes, so nothing is induced
        factor = (1.0 if ctx.method == "be" else 2.0) * self.mutual / ctx.h
        for me, other in ((self.l1, self.l2), (self.l2, self.l1)):
            _, i_other_prev = ctx.state[other.key]
            system.add(me.br, other.br, -factor)
            system.add_b(me.br, -factor * i_other_prev)

    def stamp_ac(self, system, ctx):
        z = 1j * ctx.omega * self.mutual
        system.add(self.l1.br, self.l2.br, -z)
        system.add(self.l2.br, self.l1.br, -z)

    def terminal_currents(self, x, ctx):
        return []

    def voltage(self, x, a=0, b=1):
        return 0.0

    def netlist_line(self):
        return f"{self.name} {self.l1_name} {self.l2_name} {self.value:g}"

    def describe(self):
        return f"coupling {self.name} between {self.l1_name} and {self.l2_name} (k = {self.value:g})"


class IdealTransformer(Component):
    """Vp = n Vs and Is = -n Ip, with n = Np/Ns. Lossless: power in equals power out.

    (In MiniSpice, T is the ideal transformer. SPICE uses T for transmission lines.)
    """

    letter = "T"
    kind = "ideal transformer"
    terminals = ("p+", "p-", "s+", "s-")
    n_branches = 1

    def __init__(self, name, p1, p2, s1, s2, ratio):
        super().__init__(name, [p1, p2, s1, s2])
        if ratio <= 0:
            raise ParseError(f"{name}: turns ratio must be positive")
        self.value = ratio

    @classmethod
    def parse(cls, name, tokens, models):
        positional, keywords = split_args(tokens)
        if len(positional) < 4:
            raise ParseError(f"{name}: Usage: {T_USAGE}")
        nodes = positional[:4]
        rest = positional[4:]
        if rest:
            ratio = number(rest.pop(0), f"{name} turns ratio")
        elif "n" in keywords or "ratio" in keywords:
            ratio = number(keywords.pop("n", None) or keywords.pop("ratio"), f"{name} turns ratio")
        else:
            raise ParseError(f"{name} has no turns ratio. Usage: {T_USAGE}")
        keywords.pop("ratio", None)
        reject_leftovers(name, rest, keywords, T_USAGE)
        return cls(name, *nodes, ratio)

    def dc_paths(self):
        return [(self.nodes[0], self.nodes[1]), (self.nodes[2], self.nodes[3])]

    def _stamp(self, system):
        p1, p2, s1, s2 = self.idx
        n = self.value
        # Branch unknown: primary current Ip. The secondary current is -n Ip.
        system.add(p1, self.br, 1.0)
        system.add(p2, self.br, -1.0)
        system.add(s1, self.br, -n)
        system.add(s2, self.br, n)
        # Branch row: (Vp+ - Vp-) - n (Vs+ - Vs-) = 0
        system.add(self.br, p1, 1.0)
        system.add(self.br, p2, -1.0)
        system.add(self.br, s1, -n)
        system.add(self.br, s2, n)

    def stamp(self, system, ctx):
        self._stamp(system)
        if ctx.explaining:
            ctx.note("Faraday's law", f"{self.name}: the same flux links both windings, so Vp = {self.value:g} Vs, and power in = power out gives Is = -{self.value:g} Ip.", [self.name])

    def stamp_ac(self, system, ctx):
        self._stamp(system)

    def terminal_currents(self, x, ctx):
        i = x[self.br]
        return [i, -i, -self.value * i, self.value * i]

    def netlist_line(self):
        return f"{self.name} {' '.join(self.nodes)} {self.value:g}"

    def describe(self):
        return f"ideal transformer {self.name} ({self.value:g}:1)"
