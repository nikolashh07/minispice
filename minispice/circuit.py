"""A circuit: its components, models, and the analyses its netlist asks for."""

import copy
from dataclasses import dataclass, field

from .errors import CircuitError


@dataclass
class Directive:
    """A dot-command such as .tran or .ac, kept as text until an analysis reads it."""

    kind: str
    args: list
    keywords: dict = field(default_factory=dict)
    raw: str = ""
    where: str = ""


class Circuit:
    def __init__(self, title=""):
        self.title = title
        self.components = []
        self._by_key = {}
        self.models = {}
        self.directives = []
        self.temperature = 27.0  # °C
        self.initial_conditions = {}  # node -> volts, from .ic
        self.params = {}
        self.subcircuits = {}
        self.warnings = []

    def add(self, comp):
        existing = self._by_key.get(comp.key)
        if existing is not None:
            same = "" if existing.name == comp.name else f" (names are case-insensitive, so {existing.name} and {comp.name} are the same part)"
            raise ValueError(f"{comp.name} is defined twice{same}. Give each part its own name.")
        self.components.append(comp)
        self._by_key[comp.key] = comp
        return comp

    def get(self, name):
        comp = self._by_key.get(name.lower())
        if comp is None:
            known = ", ".join(c.name for c in self.components[:20])
            raise CircuitError(f"There is no component named '{name}'. The circuit has: {known}.")
        return comp

    def has(self, name):
        return name.lower() in self._by_key

    def remove(self, name):
        comp = self.get(name)
        self.components.remove(comp)
        del self._by_key[comp.key]
        return comp

    @property
    def nodes(self):
        """Non-ground node names in the order they first appear."""
        seen = []
        for comp in self.components:
            for node in comp.nodes:
                if node != "0" and node not in seen:
                    seen.append(node)
        return seen

    @property
    def is_linear(self):
        return not any(c.nonlinear for c in self.components)

    @property
    def independent_sources(self):
        return [c for c in self.components if c.is_source]

    def find_directives(self, kind):
        return [d for d in self.directives if d.kind == kind]

    def copy(self):
        return copy.deepcopy(self)

    def with_value(self, name, value):
        """A copy with one part's main value changed. Used by sweeps, Monte Carlo and sensitivity."""
        changed = self.copy()
        changed.get(name).value = value
        return changed

    def to_netlist(self):
        lines = [f"* {self.title}" if self.title else "* MiniSpice circuit"]
        for model in self.models.values():
            params = " ".join(f"{k}={v:g}" for k, v in model.params.items())
            lines.append(f".model {model.name} {model.type}({params})")
        lines.extend(c.netlist_line() for c in self.components)
        if self.temperature != 27.0:
            lines.append(f".temp {self.temperature:g}")
        lines.extend(d.raw for d in self.directives if d.raw)
        lines.append(".end")
        return "\n".join(lines) + "\n"

    def __repr__(self):
        return f"<Circuit {self.title!r}: {len(self.components)} parts, nodes {self.nodes}>"
