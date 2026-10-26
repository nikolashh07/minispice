"""What every component has in common.

A component knows its nodes and how to stamp itself into the MNA matrix for each analysis.
The solver only ever calls these methods, so a new part type never requires solver changes.
"""

from ..units import format_eng, parse_value


def node_voltage(x, index):
    """Voltage of a node from the solution vector. Ground (index -1) is always 0 V."""
    return 0.0 if index < 0 else x[index]


class Component:
    letter = ""  # first letter of the name in a netlist
    kind = "component"
    unit = ""  # unit of the main value, for printing
    terminals = ("+", "-")
    n_branches = 0  # extra current unknowns this part adds to the matrix
    nonlinear = False
    is_source = False  # independent source (turned off for Thevenin and superposition)
    dynamic = False  # has memory in time (capacitors, inductors)

    def __init__(self, name, nodes):
        self.name = name
        self.nodes = list(nodes)
        self.value = None
        self.tol = None  # fractional tolerance for Monte Carlo, e.g. 0.05 for 5 %
        self.idx = []
        self.br = None
        self.line = None  # where in the netlist it came from, for error messages

    @property
    def key(self):
        # Names are case-insensitive, like SPICE: R1 and r1 are the same part.
        return self.name.lower()

    # ---- topology -----------------------------------------------------------------------
    def internal_nodes(self):
        return []

    def all_nodes(self):
        return self.nodes + self.internal_nodes()

    def bind(self, layout):
        self.idx = [layout.index(n) for n in self.all_nodes()]
        self.br = layout.branch_index.get(self.key)

    def check_references(self, circuit):
        """Parts that name other parts (like F1 naming V1) check those names exist here."""

    def rename_references(self, rename):
        """Called when a subcircuit is flattened, so names of referenced parts get the same prefix."""

    def dc_paths(self):
        """Pairs of nodes this part connects at DC. Used to find floating nodes."""
        return []

    def voltage_pairs(self, mode):
        """Pairs of nodes whose voltage difference this part fixes. Used to find voltage-source loops."""
        return []

    # ---- stamping -----------------------------------------------------------------------
    def stamp(self, system, ctx):
        raise NotImplementedError(f"{self.kind} can't be used in DC or transient analysis yet")

    def stamp_ac(self, system, ctx):
        raise NotImplementedError(f"{self.kind} can't be used in AC analysis yet")

    def terminal_currents(self, x, ctx):
        """Current flowing into each terminal, in amps (passive sign convention)."""
        raise NotImplementedError

    def ac_terminal_currents(self, x, ctx):
        return self.terminal_currents(x, ctx)

    # ---- time -----------------------------------------------------------------------
    def initial_state(self, x, ctx):
        """History at t = 0, from the DC operating point. None for parts without memory."""
        return None

    def update_state(self, x, ctx):
        """History after a transient step is accepted."""
        return None

    def breakpoints(self, t_stop):
        """Times where this part changes abruptly, so the time stepper lands exactly on them."""
        return []

    # ---- other analyses ---------------------------------------------------------------
    def noise_sources(self, x, ctx):
        """List of (node_a, node_b, psd) noise currents in A²/Hz. psd may be a function of frequency."""
        return []

    def region(self, x, ctx):
        """Operating region for transistors ('saturation', ...). None for simple parts."""
        return None

    # ---- text -------------------------------------------------------------------------
    def describe(self):
        if self.value is None:
            return f"{self.kind} {self.name}"
        return f"{self.kind} {self.name} ({format_eng(self.value, self.unit)})"

    def netlist_line(self):
        return f"{self.name} {' '.join(self.nodes)} {self.value:g}"

    def voltage(self, x, a=0, b=1):
        return node_voltage(x, self.idx[a]) - node_voltage(x, self.idx[b])

    def power(self, x, ctx):
        """Power absorbed: the sum of V × I over all terminals, with I flowing in.

        Because each part's power comes from the same terminal currents KCL uses, the total over
        the whole circuit is zero exactly when KCL and KVL hold (Tellegen's theorem).
        """
        currents = self.terminal_currents(x, ctx)
        return sum(node_voltage(x, i) * c for i, c in zip(self.idx, currents))

    def __repr__(self):
        return f"<{type(self).__name__} {self.name} {self.nodes} {self.value}>"


def stamp_linearized(system, idx, currents, jacobian, controls, vc0):
    """Stamp a nonlinear part as its straight-line approximation at the current guess.

    currents[k]    current into terminal k at the guess
    controls[j]    (p, n) terminal numbers; controlling voltage j is V(p) - V(n)
    jacobian[k][j] d currents[k] / d controlling voltage j
    vc0[j]         controlling voltages at the guess (after any voltage limiting)

    Each terminal current becomes I0 + sum(g * (vc - vc0)): conductances go in the matrix and
    the constant part becomes a current source on the right-hand side. This is one Newton step.
    """
    for k, row in enumerate(idx):
        if row < 0:
            continue
        constant = currents[k]
        for j, (p, n) in enumerate(controls):
            g = jacobian[k][j]
            if g == 0.0:
                continue
            system.add(row, idx[p], g)
            system.add(row, idx[n], -g)
            constant -= g * vc0[j]
        # The current leaves the node, so it moves to the right-hand side with a minus sign.
        system.add_b(row, -constant)


def stamp_small_signal(system, idx, jacobian, controls):
    """Only the conductance part of stamp_linearized: what AC and noise analysis see."""
    for k, row in enumerate(idx):
        if row < 0:
            continue
        for j, (p, n) in enumerate(controls):
            g = jacobian[k][j]
            if g != 0.0:
                system.add(row, idx[p], g)
                system.add(row, idx[n], -g)


class ParseError(ValueError):
    """A problem with one netlist line. The parser adds the line number."""


def split_args(tokens):
    """Separate positional tokens from key=value tokens (keys lowercased)."""
    positional, keywords = [], {}
    for token in tokens:
        if "=" in token:
            key, _, value = token.partition("=")
            keywords[key.lower()] = value
        else:
            positional.append(token)
    return positional, keywords


def number(text, what):
    """parse_value with an error message that says which value was wrong."""
    try:
        return parse_value(text)
    except ValueError:
        raise ParseError(f"{what} '{text}' is not a number (examples: 1k, 4.7u, 10meg)") from None


def take_keyword(keywords, name, what, default=None):
    if name not in keywords:
        return default
    return number(keywords.pop(name), what)


def reject_leftovers(name, positional, keywords, usage):
    if positional:
        raise ParseError(f"{name}: unexpected '{' '.join(positional)}'. Usage: {usage}")
    if keywords:
        raise ParseError(f"{name}: unknown option(s) {', '.join(k + '=' for k in keywords)}. Usage: {usage}")


def need_nodes(name, positional, count, usage):
    if len(positional) < count:
        raise ParseError(f"{name} needs {count} nodes. Usage: {usage}")
    return [positional.pop(0) for _ in range(count)]


def take_tolerance(comp, keywords):
    if "tol" in keywords:
        comp.tol = number(keywords.pop("tol"), "tolerance")
        if comp.tol > 1:
            # "tol=5" almost certainly means 5 %, not 500 %.
            comp.tol /= 100
