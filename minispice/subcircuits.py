"""Reusable circuit blocks: .subckt definitions and the X lines that use them.

A subcircuit is expanded ("flattened") when it is used: each of its parts is copied into the main
circuit with a unique name, its ports are wired to the X line's nodes, and its private nodes get
the instance name as a prefix. The solver never sees subcircuits, only ordinary parts.

    .subckt divider in out
    R1 in out 1k
    R2 out 0 1k
    .ends
    X1 a b divider       -> parts R1.X1 and R2.X1, private nodes like x1.mid
"""

from dataclasses import dataclass, field

from .components.base import ParseError, split_args

MAX_DEPTH = 20


@dataclass
class SubcircuitDef:
    name: str
    ports: list
    defaults: dict = field(default_factory=dict)
    lines: list = field(default_factory=list)  # [(where, text)]
    where: str = ""


def collect_subcircuits(lines, definitions, problems):
    """Move .subckt ... .ends blocks out of the line list and into definitions."""
    from .netlist import evaluate_expression, normalize_node, tokenize

    out = []
    current = None
    for where, line in lines:
        lower = line.lower()
        if lower.startswith(".subckt"):
            if current is not None:
                problems.append((where, f"a .subckt can't be defined inside another (.subckt {current.name} has no .ends yet)"))
                continue
            tokens = tokenize(line)
            if len(tokens) < 2:
                problems.append((where, "Usage: .subckt <name> <port> <port> ... [param=default ...]"))
                continue
            positional, keywords = split_args([t for t in tokens[2:] if t.lower() != "params:"])
            defaults = {}
            try:
                for key, value in keywords.items():
                    defaults[key] = evaluate_expression(value.strip("{}"), {})
            except ParseError as error:
                problems.append((where, str(error)))
            current = SubcircuitDef(tokens[1].lower(), [normalize_node(p) for p in positional], defaults, [], where)
        elif lower.startswith(".ends"):
            if current is None:
                problems.append((where, ".ends without a matching .subckt"))
            else:
                definitions[current.name] = current
                current = None
        elif current is not None:
            current.lines.append((where, line))
        else:
            out.append((where, line))
    if current is not None:
        problems.append((current.where, f".subckt {current.name} has no .ends"))
    return out


def expand_instance(line, circuit, where, path="", node_map=None, depth=0):
    """Turn one X line into the list of ordinary parts it stands for."""
    from .netlist import evaluate_expression, normalize_node, parse_element, parse_model, substitute_params, tokenize

    if depth > MAX_DEPTH:
        raise ParseError("subcircuits nest more than 20 deep; does a subcircuit use itself?")
    map_node = node_map or normalize_node
    tokens = tokenize(line)
    xname = tokens[0]
    positional, keywords = split_args([t for t in tokens[1:] if t.lower() != "params:"])
    if not positional:
        raise ParseError(f"Usage: {xname} <node> <node> ... <subcircuit name> [param=value ...]")
    sub_name = positional[-1].lower()
    nodes = [map_node(n) for n in positional[:-1]]
    definition = circuit.subcircuits.get(sub_name)
    if definition is None:
        known = ", ".join(circuit.subcircuits) or "none defined"
        raise ParseError(f"{xname} uses subcircuit '{positional[-1]}', which isn't defined (.subckt). Known: {known}")
    if len(nodes) != len(definition.ports):
        raise ParseError(
            f"{xname}: subcircuit '{sub_name}' has {len(definition.ports)} ports ({' '.join(definition.ports)}) "
            f"but {len(nodes)} nodes were given"
        )

    instance = f"{path}.{xname}" if path else xname
    ports = dict(zip(definition.ports, nodes))

    def inner_node(node):
        node = normalize_node(node)
        if node == "0":
            return "0"  # ground is shared by the whole circuit
        if node in ports:
            return ports[node]
        return f"{instance.lower()}.{node}"

    params = dict(circuit.params)
    params.update(definition.defaults)
    for key, value in keywords.items():
        params[key] = evaluate_expression(value.strip("{}"), circuit.params)

    parts = []
    for body_where, body_line in definition.lines:
        body_line = substitute_params(body_line, params)
        lower = body_line.lower()
        if lower.startswith(".model"):
            model = parse_model(body_line)
            circuit.models.setdefault(model.name, model)
        elif lower.startswith("."):
            raise ParseError(f"{body_where} (in .subckt {sub_name}): only parts and .model lines can go inside a subcircuit")
        elif lower.startswith("x"):
            parts.extend(expand_instance(body_line, circuit, body_where, instance, inner_node, depth + 1))
        else:
            try:
                comp = parse_element(body_line, circuit.models)
            except ParseError as error:
                raise ParseError(f"in .subckt {sub_name} ({body_where}): {error}") from None
            comp.nodes = [inner_node(n) for n in comp.nodes]
            original = comp.name
            comp.name = f"{original}.{instance}"
            comp.rename_references(lambda ref: f"{ref}.{instance}")
            parts.append(comp)
    return parts
