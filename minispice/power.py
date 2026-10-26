"""Joule heating per component and whole-circuit power balance.

Sign convention (passive): positive current flows into a part's + terminal, and V × I is the
power it absorbs. A part that delivers power, like a battery being discharged, shows negative
power. By conservation of energy (Tellegen's theorem) all the powers add up to zero.
"""

from dataclasses import dataclass, field

from .units import format_eng


@dataclass
class PowerRow:
    name: str
    kind: str
    power: float  # watts absorbed
    rating: float = None
    overheating: bool = False


@dataclass
class PowerReport:
    rows: list
    absorbed: float  # total of the positive powers
    delivered: float  # total of the negative powers, as a positive number
    imbalance: float  # sum of all powers; zero when energy is conserved
    warnings: list = field(default_factory=list)

    @property
    def balanced(self):
        return abs(self.imbalance) <= 1e-6 * max(self.absorbed, self.delivered) + 1e-12

    def summary(self):
        status = "balanced" if self.balanced else "NOT balanced"
        return (
            f"Sources deliver {format_eng(self.delivered, 'W')}, parts absorb {format_eng(self.absorbed, 'W')}: "
            f"{status} (sum of all powers = {format_eng(self.imbalance, 'W')})"
        )


def power_report(solution):
    rows = []
    warnings = []
    for comp in solution.circuit.components:
        p = float(comp.power(solution.x, solution.ctx))
        rating = getattr(comp, "rating", None)
        hot = rating is not None and p > rating
        rows.append(PowerRow(comp.name, comp.kind, p, rating, hot))
        if hot:
            warnings.append(
                f"{comp.name} absorbs {format_eng(p, 'W')} but is rated for {format_eng(rating, 'W')}. It will "
                f"overheat: use a part rated {format_eng(_next_rating(p), 'W')} or more, or reduce the current."
            )
    absorbed = sum(r.power for r in rows if r.power > 0)
    delivered = -sum(r.power for r in rows if r.power < 0)
    imbalance = sum(r.power for r in rows)
    return PowerReport(rows, absorbed, delivered, imbalance, warnings)


def _next_rating(power):
    """Standard resistor power ratings, so the advice names a part you can actually buy."""
    for rating in (0.125, 0.25, 0.5, 1, 2, 3, 5, 10, 25, 50, 100):
        if rating >= power:
            return rating
    return power
