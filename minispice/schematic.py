"""Auto-drawn schematics with schemdraw, optionally annotated with simulation results.

Laying out any circuit neatly is a hard problem (it's graph drawing), so this uses a simple
scheme that is always readable for series and parallel circuits and still correct for others:

  * every non-ground node is a horizontal bus line, placed left to right in connection order
  * a part from a node to ground hangs straight down from that node's bus, with a ground symbol
  * a part between two neighbouring nodes sits on the line between their buses
  * any other two-terminal part bridges over the buses in an arc
  * transistors, op-amps and transformers sit in a row above, wired to their nodes

With a Solution, nodes are labeled with voltages, parts with current and power, wires are
colored by voltage like a heat map, and parts over their power rating are drawn in red.
"""

import math

from .units import format_eng

DX = 3.0  # spacing between connection points on a bus
GAP = 3.0  # room for one part between neighbouring buses
DROP = 3.0  # length of a part hanging to ground
ARC = 2.5  # height between arc levels
HIGHLIGHT = "#e67e00"


def _schemdraw():
    try:
        import schemdraw
        import schemdraw.elements as elm
    except ImportError:
        raise ImportError("Schematics need the schemdraw library: pip install schemdraw") from None
    schemdraw.use("matplotlib")
    return schemdraw, elm


def node_order(circuit):
    """Non-ground nodes in breadth-first order from the first source, so the drawing reads left to right."""
    neighbours = {}
    for comp in circuit.components:
        nodes = [n for n in comp.nodes if n != "0"]
        for a in nodes:
            for b in nodes:
                if a != b:
                    neighbours.setdefault(a, []).append(b)
    all_nodes = circuit.nodes
    sources = [c for c in circuit.components if c.is_source]
    start = next((n for c in sources for n in c.nodes if n != "0"), all_nodes[0] if all_nodes else None)
    order = []
    for seed in [start] + all_nodes:
        if seed is None or seed in order:
            continue
        queue = [seed]
        while queue:
            node = queue.pop(0)
            if node in order:
                continue
            order.append(node)
            queue.extend(n for n in neighbours.get(node, []) if n not in order)
    return order


def _two_terminal_element(elm, comp):
    letter = comp.letter
    if letter == "R":
        return elm.Resistor()
    if letter == "C":
        return elm.Capacitor()
    if letter == "L":
        return elm.Inductor2()
    if letter == "V":
        return elm.SourceV()
    if letter == "I":
        return elm.SourceI()
    if letter == "D":
        name = comp.model.name.lower()
        if name.startswith("led"):
            return elm.LED()
        if math.isfinite(comp.bv) and comp.bv < 50:
            return elm.Zener()
        return elm.Diode()
    if letter == "S":
        return elm.Switch()
    if letter in ("E", "H"):
        return elm.SourceControlledV()
    if letter in ("G", "F"):
        return elm.SourceControlledI()
    return elm.Resistor()


def _endpoints(comp, plus_end, minus_end):
    """schemdraw draws a voltage source's + sign at the element's end point, so voltage sources go
    from - to +. Everything else goes from its first node to its second (a current source's arrow
    then points the way SPICE pushes the current, a diode points from anode to cathode)."""
    if comp.letter in ("V", "E", "H"):
        return minus_end, plus_end
    return plus_end, minus_end


def _label(comp):
    text = comp.name
    if comp.letter in ("R", "C", "L", "V", "I") and comp.value is not None:
        text += "\n" + format_eng(comp.value, comp.unit)
    elif comp.letter == "D":
        text += f"\n{comp.model.name}"
    elif comp.letter in ("E", "G"):
        text += f"\n{comp.value:g}·V({comp.nodes[2]},{comp.nodes[3]})"
    elif comp.letter in ("F", "H"):
        text += f"\n{comp.value:g}·I({comp.control})"
    return text


def _result_label(comp, solution):
    current = solution.i(comp.name)
    power = solution.p(comp.name)
    return f"{format_eng(current, 'A')}\n{format_eng(power, 'W')}"


class _Painter:
    """Chooses wire colors from node voltages (a blue-to-red heat map)."""

    def __init__(self, solution):
        self.solution = solution
        if solution is None:
            return
        import matplotlib

        voltages = list(solution.node_voltages.values()) + [0.0]
        self.low, self.high = min(voltages), max(voltages)
        self.cmap = matplotlib.colormaps["coolwarm"]

    def color(self, node):
        if self.solution is None:
            return "black"
        from matplotlib.colors import to_hex

        v = 0.0 if node == "0" else self.solution.v(node)
        span = self.high - self.low
        return to_hex(self.cmap(0.5 if span == 0 else (v - self.low) / span))


def draw_schematic(circuit, path=None, solution=None, title=None, highlight=()):
    """Draw the circuit (with results if a Solution is given) and save it to path (.svg or .png).

    Parts named in highlight are drawn in orange, which explain mode uses to point at each step.
    """
    highlight = {name.lower() for name in highlight}
    schemdraw, elm = _schemdraw()
    paint = _Painter(solution)
    order = node_order(circuit)
    position = {n: i for i, n in enumerate(order)}

    # Decide how each part is drawn.
    downs, chain, arcs, blocks = [], {}, [], []
    for comp in circuit.components:
        if comp.letter == "K":
            continue  # coupling is shown in the inductors' labels
        nodes = comp.nodes if comp.letter not in ("E", "G") else comp.nodes[:2]
        if len(nodes) == 2 and comp.letter != "T":
            a, b = nodes
            if a == "0" and b == "0":
                continue
            if a == "0" or b == "0":
                downs.append(comp)
            elif abs(position[a] - position[b]) == 1 and (min(a, b, key=position.get), max(a, b, key=position.get)) not in chain:
                chain[(min(a, b, key=position.get), max(a, b, key=position.get))] = comp
            else:
                arcs.append(comp)
        else:
            blocks.append(comp)

    # Each down part, arc end and block terminal needs its own connection point on a bus.
    slots = {n: [] for n in order}
    for comp in downs:
        slots[next(n for n in comp.nodes if n != "0")].append(("down", comp))
    for comp in arcs:
        for n in comp.nodes[:2]:
            slots[n].append(("arc", comp))
    for comp in blocks:
        for n in comp.nodes:
            if n != "0":
                slots[n].append(("block", comp))

    bus = {}
    x = 0.0
    for n in order:
        width = max(0, len(slots[n]) - 1) * DX
        bus[n] = (x, x + width)
        x += width + GAP
    slot_x = {}
    for n in order:
        for k, item in enumerate(slots[n]):
            slot_x.setdefault((n, id(item[1])), []).append(bus[n][0] + k * DX)

    def take_slot(node, comp):
        return slot_x[(node, id(comp))].pop(0)

    drawing = schemdraw.Drawing(show=False)
    drawing.config(fontsize=10)

    def wire(p, q, node):
        if p != q:
            drawing.add(elm.Line().endpoints(p, q).color(paint.color(node)))

    def mark_part(element, comp):
        hot = solution is not None and getattr(comp, "rating", None) is not None and solution.p(comp.name) > comp.rating
        element.color("red" if hot else HIGHLIGHT if comp.key in highlight else "black")
        element.label(_label(comp), loc="top", fontsize=9)
        if solution is not None and comp.letter in ("R", "C", "L", "V", "I", "D", "S", "E", "G", "F", "H"):
            extra = _result_label(comp, solution) + ("\nOVERHEATING" if hot else "")
            element.label(extra, loc="bottom", fontsize=8, color="red" if hot else "dimgray")

    # Buses and node labels.
    for n in order:
        x0, x1 = bus[n]
        wire((x0, 0), (x1, 0), n)
        drawing.add(elm.Dot().at((x0, 0)).color(paint.color(n)))
        text = n if solution is None else f"{n}: {format_eng(solution.v(n), 'V')}"
        drawing.add(elm.Label().at((x0, 0.45)).label(text, fontsize=9, color="navy"))

    # Parts between neighbouring nodes, along the bus line.
    for (a, b), comp in chain.items():
        start, end = (bus[a][1], 0), (bus[b][0], 0)
        first, second = _endpoints(comp, *((start, end) if comp.nodes[0] == a else (end, start)))
        element = _two_terminal_element(elm, comp).endpoints(first, second)
        mark_part(element, comp)
        drawing.add(element)

    # Parts to ground, hanging down.
    for comp in downs:
        node = next(n for n in comp.nodes if n != "0")
        x0 = take_slot(node, comp)
        top, bottom = (x0, 0), (x0, -DROP)
        first, second = _endpoints(comp, *((top, bottom) if comp.nodes[0] == node else (bottom, top)))
        element = _two_terminal_element(elm, comp).endpoints(first, second)
        mark_part(element, comp)
        drawing.add(element)
        drawing.add(elm.Ground().at(bottom))

    # Other two-terminal parts bridge over the buses; each level holds non-overlapping arcs.
    levels = []
    for comp in arcs:
        a, b = comp.nodes[:2]
        xa, xb = take_slot(a, comp), take_slot(b, comp)
        lo, hi = min(xa, xb), max(xa, xb)
        level = next((i for i, used in enumerate(levels) if all(hi < u_lo or lo > u_hi for u_lo, u_hi in used)), None)
        if level is None:
            levels.append([])
            level = len(levels) - 1
        levels[level].append((lo - 0.1, hi + 0.1))
        y = ARC * (level + 1)
        wire((xa, 0), (xa, y), a)
        wire((xb, 0), (xb, y), b)
        if abs(xb - xa) < DX:
            # Too short to hold a part: lift the far end sideways.
            xb_part = xa + DX
            wire((xb, y), (xb_part, y), b)
        else:
            xb_part = xb
        element = _two_terminal_element(elm, comp).endpoints(*_endpoints(comp, (xa, y), (xb_part, y)))
        mark_part(element, comp)
        drawing.add(element)

    # Multi-terminal parts in a row above everything, wired to their nodes.
    y_block = ARC * (len(levels) + 1) + 3.0
    x_next = 0.0
    for comp in blocks:
        element, anchors = _block(elm, comp)
        node_xs = [bus[n][0] for n in comp.nodes if n != "0"]
        x_at = max(x_next, sum(node_xs) / len(node_xs) if node_xs else x_next)
        element.at((x_at, y_block)).color(HIGHLIGHT if comp.key in highlight else "black")
        element.label(comp.name + (f"\n{comp.model.name}" if getattr(comp, "model", None) else ""), loc="top", fontsize=9)
        drawing.add(element)
        x_next = x_at + 6.0
        for node, anchor in zip(comp.nodes, anchors):
            tx, ty = element.absanchors[anchor]
            if node == "0":
                drawing.add(elm.Line().endpoints((tx, ty), (tx, ty - 0.6)).color(paint.color("0")))
                drawing.add(elm.Ground().at((tx, ty - 0.6)))
                continue
            sx = take_slot(node, comp)
            wire((sx, 0), (sx, ty), node)
            wire((sx, ty), (tx, ty), node)
        if solution is not None:
            region = solution.region(comp.name)
            if region:
                drawing.add(elm.Label().at((x_at, y_block - 2.2)).label(region, fontsize=8, color="dimgray"))

    if title or circuit.title:
        drawing.add(elm.Label().at((0, y_block + 3.5 if blocks else ARC * (len(levels) + 1) + 1.5)).label(title or circuit.title, fontsize=12, halign="left"))
    if solution is not None:
        drawing.add(elm.Label().at((0, -DROP - 2.0)).label("wire color: blue = lowest voltage, red = highest", fontsize=8, halign="left", color="dimgray"))
    if path:
        drawing.save(path)
    return drawing


def _block(elm, comp):
    """(schemdraw element, anchor name for each of the part's nodes in order)."""
    if comp.letter == "Q":
        element = elm.BjtNpn() if comp.polarity > 0 else elm.BjtPnp()
        return element.anchor("base"), ["collector", "base", "emitter"]
    if comp.letter == "M":
        element = elm.NFet() if comp.polarity > 0 else elm.PFet()
        return element.anchor("gate"), ["drain", "gate", "source"]
    if comp.letter == "U":
        return elm.Opamp().anchor("in1"), ["in2", "in1", "out"]
    if comp.letter == "T":
        return elm.Transformer().anchor("p1"), ["p1", "p2", "s1", "s2"]
    raise ValueError(f"no drawing for {comp.kind}")
