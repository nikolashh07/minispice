"""Thevenin, Norton, superposition, and maximum power transfer.

All of them rely on the circuit being linear: then any two-terminal view of it behaves like one
source and one resistor, and the response to several sources is the sum of the responses to each.
"""

from dataclasses import dataclass

from .analysis.dc import operating_point
from .components.sources import CurrentSource
from .errors import CircuitError
from .netlist import normalize_node
from .units import format_eng

TEST_SOURCE = "I_theorem_test"


@dataclass
class Thevenin:
    a: str
    b: str
    vth: float  # open-circuit voltage V(a) - V(b)
    rth: float  # resistance seen between a and b with the sources turned off

    @property
    def norton_current(self):
        """Short-circuit current from a to b."""
        if self.rth == 0:
            raise CircuitError(
                f"Between {self.a} and {self.b} there is an ideal voltage source (Rth = 0), so the short-circuit "
                "current would be infinite and no Norton equivalent exists."
            )
        return self.vth / self.rth

    @property
    def max_power_load(self):
        return self.rth

    @property
    def max_power(self):
        if self.rth <= 0:
            raise CircuitError("Maximum power transfer needs a positive Thevenin resistance.")
        return self.vth ** 2 / (4 * self.rth)

    def describe(self):
        return (
            f"Thevenin equivalent between {self.a} and {self.b}: Vth = {format_eng(self.vth, 'V')} "
            f"in series with Rth = {format_eng(self.rth, 'Ω')}"
        )


def _require_linear(circuit):
    if not circuit.is_linear:
        names = ", ".join(c.name for c in circuit.components if c.nonlinear)
        raise CircuitError(
            f"Thevenin, Norton and superposition only apply to linear circuits, and {names} "
            "is nonlinear (its current isn't proportional to its voltage)."
        )


def _prepare(circuit, a, b, remove):
    _require_linear(circuit)
    work = circuit.copy()
    for name in remove:
        work.remove(name)
    a, b = normalize_node(a), normalize_node(b)
    present = {n for comp in work.components for n in comp.nodes}
    for node in (a, b):
        if node not in present:
            raise CircuitError(f"Node '{node}' isn't connected to anything" + (" after removing " + ", ".join(remove) if remove else ""))
    if a == b:
        raise CircuitError("Pick two different nodes for the equivalent circuit.")
    return work, a, b


def thevenin(circuit, a, b="0", remove=()):
    """Thevenin equivalent seen from nodes a and b (optionally after removing a load)."""
    work, a, b = _prepare(circuit, a, b, remove)

    # Vth: with nothing connected across a-b, the voltage there is the open-circuit voltage.
    vth = operating_point(work).v(a, b)

    # Rth: turn every independent source off (voltage sources become shorts, current sources
    # become opens), push 1 A into a and out of b, and see what voltage that takes. Dependent
    # sources stay on, which is why this works when the "combine resistors" method doesn't.
    work.add(CurrentSource(TEST_SOURCE, b, a, 1.0))
    test = operating_point(work, sources_on={TEST_SOURCE.lower()})
    rth = test.v(a, b) / 1.0
    return Thevenin(a, b, vth, rth)


def norton(circuit, a, b="0", remove=()):
    """Norton equivalent: (short-circuit current In, Rn) with In flowing from a to b through the short."""
    th = thevenin(circuit, a, b, remove)
    return th.norton_current, th.rth


@dataclass
class Superposition:
    total: object  # Solution with every source on
    parts: dict  # source name -> Solution with only that source on

    def node_breakdown(self):
        """{node: (total, {source: contribution})}"""
        out = {}
        for node in self.total.node_voltages:
            out[node] = (self.total.v(node), {name: s.v(node) for name, s in self.parts.items()})
        return out

    def max_error(self):
        """Largest gap between the total and the sum of the parts. Zero for a linear circuit."""
        worst = 0.0
        for total, contributions in self.node_breakdown().values():
            worst = max(worst, abs(total - sum(contributions.values())))
        for comp in self.total.circuit.components:
            total = self.total.i(comp.name)
            worst = max(worst, abs(total - sum(s.i(comp.name) for s in self.parts.values())))
        return worst


def superposition(circuit):
    """Solve once per independent source with the others turned off, and check the parts add up."""
    _require_linear(circuit)
    work = circuit
    sources = work.independent_sources
    if not sources:
        raise CircuitError("Superposition needs at least one independent source.")
    total = operating_point(work)
    parts = {s.name: operating_point(work, sources_on={s.key}) for s in sources}
    return Superposition(total, parts)


def max_power_transfer(circuit, a, b="0", remove=()):
    """The load resistance that draws the most power from a-b, and that power: RL = Rth, P = Vth²/(4 Rth)."""
    th = thevenin(circuit, a, b, remove)
    return th.max_power_load, th.max_power, th
