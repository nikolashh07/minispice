"""Builds and solves the circuit matrix with modified nodal analysis (MNA).

The unknowns are one voltage per non-ground node, then one current per "branch". A branch
belongs to a part whose current can't be written from node voltages alone, like a voltage
source. Each node row of the matrix is KCL at that node, and each branch row is that part's
own voltage equation (KVL). Parts add themselves to the matrix through their stamp() method,
so this file never needs to know what a resistor or a diode is.
"""

import numpy as np

from .errors import CircuitError

GROUND = -1

# Above this many unknowns a dense matrix wastes time and memory on zeros (Phase 19).
SPARSE_THRESHOLD = 150


class Layout:
    """Maps node names and branch currents to matrix rows. Built once per circuit."""

    def __init__(self, circuit):
        self.circuit = circuit
        self.nodes = []
        self.node_index = {}
        for comp in circuit.components:
            for node in comp.all_nodes():
                if node != "0" and node not in self.node_index:
                    self.node_index[node] = len(self.nodes)
                    self.nodes.append(node)

        self.branch_labels = []
        self.branch_index = {}
        first_branch = len(self.nodes)
        for comp in circuit.components:
            if comp.n_branches:
                self.branch_index[comp.key] = first_branch + len(self.branch_labels)
                for k in range(comp.n_branches):
                    suffix = "" if comp.n_branches == 1 else f"#{k}"
                    self.branch_labels.append(f"I({comp.name}{suffix})")
        self.size = len(self.nodes) + len(self.branch_labels)

        for comp in circuit.components:
            comp.bind(self)

    def index(self, node):
        if node == "0":
            return GROUND
        return self.node_index[node]

    def unknown_names(self):
        return [f"V({n})" for n in self.nodes] + self.branch_labels


class MNASystem:
    """The matrix equation A x = b, collected as (row, col, value) entries.

    Collecting entries instead of writing into a matrix lets the same stamps build a dense
    numpy array for small circuits or a scipy sparse matrix for big ones.
    """

    def __init__(self, size, dtype=float):
        self.size = size
        self.dtype = dtype
        self.rows = []
        self.cols = []
        self.vals = []
        self.b = np.zeros(size, dtype=dtype)

    def add(self, row, col, value):
        # Ground is the reference (0 V), so it has no row or column.
        if row >= 0 and col >= 0:
            self.rows.append(row)
            self.cols.append(col)
            self.vals.append(value)

    def add_b(self, row, value):
        if row >= 0:
            self.b[row] += value

    def conductance(self, a, b, g):
        """Stamp a conductance g between nodes a and b."""
        self.add(a, a, g)
        self.add(b, b, g)
        self.add(a, b, -g)
        self.add(b, a, -g)

    def current_source(self, a, b, current):
        """A current that flows out of node a, through the part, and into node b."""
        self.add_b(a, -current)
        self.add_b(b, current)

    def dense(self):
        matrix = np.zeros((self.size, self.size), dtype=self.dtype)
        if self.vals:
            np.add.at(matrix, (np.array(self.rows), np.array(self.cols)), np.array(self.vals, dtype=self.dtype))
        return matrix

    def sparse(self):
        from scipy.sparse import csc_matrix

        # csc_matrix sums duplicate entries, which is exactly how stamps combine.
        return csc_matrix(
            (np.array(self.vals, dtype=self.dtype), (np.array(self.rows), np.array(self.cols))),
            shape=(self.size, self.size),
        )

    def solve(self, layout=None, sparse=None):
        if self.size == 0:
            return np.zeros(0, dtype=self.dtype)
        if sparse is None:
            sparse = self.size > SPARSE_THRESHOLD and _have_scipy()
        if sparse:
            return _solve_sparse(self, layout)
        return _solve_dense(self.dense(), self.b, layout)


def _have_scipy():
    try:
        import scipy.sparse  # noqa: F401
        return True
    except ImportError:
        return False


def _solve_dense(matrix, b, layout):
    try:
        x = np.linalg.solve(matrix, b)
    except np.linalg.LinAlgError:
        raise CircuitError(_singular_message(matrix, layout)) from None
    if not np.all(np.isfinite(x)):
        raise CircuitError(_singular_message(matrix, layout))
    return x


def _solve_sparse(system, layout):
    import warnings

    from scipy.sparse.linalg import MatrixRankWarning, spsolve

    with warnings.catch_warnings():
        warnings.simplefilter("error", MatrixRankWarning)
        try:
            x = spsolve(system.sparse(), system.b)
        except (MatrixRankWarning, RuntimeError):
            x = None
    if x is None or not np.all(np.isfinite(x)):
        message = "The circuit matrix is singular, so the circuit has no unique solution."
        if system.size <= 2000:
            message = _singular_message(system.dense(), layout)
        raise CircuitError(message)
    return np.asarray(x, dtype=system.dtype)


def _singular_message(matrix, layout):
    message = (
        "The circuit matrix is singular, so the circuit has no unique solution. "
        "Common causes: a node with no path to ground, a loop of voltage sources or inductors, "
        "or a node that only touches current sources or capacitors."
    )
    if layout is None or matrix.size == 0:
        return message
    # The null vector of a singular matrix shows which unknowns are undetermined.
    try:
        _, s, vh = np.linalg.svd(matrix)
        null = np.abs(vh[-1])
        names = layout.unknown_names()
        suspects = [names[i] for i in np.argsort(-null)[:4] if null[i] > 0.1 * null.max()]
        if suspects:
            message += " The problem involves: " + ", ".join(suspects) + "."
    except np.linalg.LinAlgError:
        pass
    return message


def assemble(components, layout, ctx, dtype=float):
    system = MNASystem(layout.size, dtype=dtype)
    for comp in components:
        if ctx.mode == "ac":
            comp.stamp_ac(system, ctx)
        else:
            comp.stamp(system, ctx)
    return system


def check_dc_topology(circuit):
    """Find the two classic reasons a DC circuit can't be solved and explain them in words.

    1. A node with no DC path to ground: nothing fixes its voltage (KCL gives no equation that pins it).
    2. A loop of voltage sources or inductors: KVL either contradicts itself, or the current
       around the loop could be anything.
    """
    if not circuit.components:
        raise CircuitError("The circuit is empty. Add some components first.")
    all_nodes = {n for comp in circuit.components for n in comp.all_nodes()}
    if "0" not in all_nodes:
        raise CircuitError(
            "Nothing is connected to ground (node 0). Every circuit needs a reference node: "
            "connect one side of your source to 0 (or gnd)."
        )

    # Union-find over parts that conduct DC.
    parent = {n: n for n in all_nodes}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for comp in circuit.components:
        for a, b in comp.dc_paths():
            parent[find(a)] = find(b)
    floating = sorted(n for n in all_nodes if find(n) != find("0"))
    if floating:
        names = ", ".join(floating)
        raise CircuitError(
            f"Node(s) {names} have no DC path to ground, so their voltage is undefined. "
            "This happens when a node only touches capacitors, current sources, op-amp inputs or "
            "MOSFET gates, or when part of the circuit isn't connected to the rest. Connect it to "
            "the circuit, or add a large resistor (like 1G) from it to ground."
        )

    # Loops of voltage-defining parts: adding an edge between two already-joined nodes closes a loop.
    graph = {}
    for comp in circuit.components:
        for a, b in comp.voltage_pairs("dc"):
            path = _find_path(graph, a, b)
            if path is not None:
                loop = sorted(set(path + [comp.name]))
                raise CircuitError(
                    f"{', '.join(loop)} form a loop of voltage sources and/or inductors (at DC an "
                    "inductor is a short circuit). Around that loop KVL either contradicts itself "
                    "or leaves the loop current undefined. Add a small resistor in the loop."
                )
            graph.setdefault(a, []).append((b, comp.name))
            graph.setdefault(b, []).append((a, comp.name))


def _find_path(graph, start, goal):
    """Return the names of the parts on a path from start to goal, or None."""
    if start == goal:
        return []
    seen = {start}
    stack = [(start, [])]
    while stack:
        node, names = stack.pop()
        for nxt, name in graph.get(node, []):
            if nxt == goal:
                return names + [name]
            if nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, names + [name]))
    return None
