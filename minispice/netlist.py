"""Reads netlist text and turns each line into a component object.

Format (node 0, or gnd, is ground):

    * comment
    V1 1 0 DC 10
    R1 1 2 1k
    R2 2 0 1k
    .op

Names and nodes are case-insensitive, as in SPICE. Every line is checked before anything is
reported, so one error message lists every problem with its line number.
"""

import ast
import math
import os
import re

from .circuit import Circuit, Directive
from .components import REGISTRY
from .components.base import ParseError, split_args
from .components.models import MODEL_TYPES, Model
from .errors import NetlistError
from .units import parse_value

GROUND_NAMES = {"0", "gnd", "ground"}

ANALYSES = {"op", "dc", "tran", "ac", "four", "noise", "step", "mc", "sens"}
# Lines that other simulators use for output and options. They don't change the circuit, so skip them.
IGNORED = {"print", "plot", "probe", "save", "width", "meas", "measure", "option", "options", "global", "backanno", "nodeset"}


def load(path):
    """Read a netlist file. Paths in .include lines are relative to this file."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    return parse(text, source=os.path.basename(path), base_dir=os.path.dirname(os.path.abspath(path)))


def parse(text, source="netlist", base_dir=None):
    problems = []
    lines = _logical_lines(text, "")
    lines = _expand_includes(lines, base_dir, problems, depth=0)
    circuit = Circuit()

    lines = _take_title(lines, circuit)
    lines = _skip_control_blocks(lines)
    lines = _truncate_at_end(lines)

    # .param first, so values like {2*rbase} can be used anywhere, before or after the definition.
    remaining = []
    for where, line in lines:
        if line.lower().startswith(".param"):
            try:
                _read_params(line, circuit.params)
            except ParseError as error:
                problems.append((where, str(error)))
        else:
            remaining.append((where, line))

    # .subckt bodies are kept as text and expanded each time an X line uses them.
    from .subcircuits import collect_subcircuits, expand_instance

    remaining = collect_subcircuits(remaining, circuit.subcircuits, problems)

    # .model next, so a part can use a model defined further down the file.
    body = []
    for where, line in remaining:
        if line.lower().startswith(".model"):
            try:
                model = parse_model(substitute_params(line, circuit.params))
                circuit.models[model.name] = model
            except ParseError as error:
                problems.append((where, str(error)))
        else:
            body.append((where, line))

    for where, line in body:
        try:
            line = substitute_params(line, circuit.params)
            if line.startswith("."):
                _read_directive(line, where, circuit)
            elif line[0].lower() == "x":
                for comp in expand_instance(line, circuit, where):
                    _add(circuit, comp, where)
            else:
                comp = parse_element(line, circuit.models)
                _add(circuit, comp, where)
        except (ParseError, ValueError) as error:
            problems.append((where, str(error)))

    # Parts that refer to other parts by name (F, H, K) can only be checked once everything is read.
    for comp in circuit.components:
        try:
            comp.check_references(circuit)
        except ParseError as error:
            problems.append((comp.line, str(error)))

    if problems:
        raise NetlistError(problems, source)
    return circuit


def _add(circuit, comp, where):
    comp.line = where
    circuit.add(comp)


def tokenize(line):
    """Split a line into words. Parentheses and commas are just separators: PULSE(0 5 1m) = PULSE 0 5 1m."""
    line = re.sub(r"\s*=\s*", "=", line)
    line = re.sub(r"[(),]", " ", line)
    return line.split()


def normalize_node(node):
    node = node.lower()
    return "0" if node in GROUND_NAMES else node


def parse_element(line, models):
    tokens = tokenize(line)
    name = tokens[0]
    letter = name[0].upper()
    cls = REGISTRY.get(letter)
    if cls is None:
        known = ", ".join(f"{k} ({v.kind})" for k, v in sorted(REGISTRY.items()))
        raise ParseError(f"'{name}': no component type starts with '{letter}'. Known types: {known}, X (subcircuit)")
    if len(name) < 1:
        raise ParseError("component has no name")
    rest = [t.lower() for t in tokens[1:]]
    comp = cls.parse(name, rest, models)
    comp.nodes = [normalize_node(n) for n in comp.nodes]
    return comp


def parse_model(line):
    tokens = tokenize(line)
    if len(tokens) < 3:
        raise ParseError("Usage: .model <name> <type>(<param>=<value> ...), types: " + ", ".join(t.upper() for t in MODEL_TYPES))
    name, kind = tokens[1].lower(), tokens[2].lower()
    if kind not in MODEL_TYPES:
        raise ParseError(f".model {tokens[1]}: type '{tokens[2]}' isn't supported. Supported types: {', '.join(t.upper() for t in MODEL_TYPES)}")
    positional, keywords = split_args(tokens[3:])
    if positional:
        raise ParseError(f".model {tokens[1]}: expected <param>=<value>, got '{positional[0]}'")
    params = {}
    for key, value in keywords.items():
        try:
            params[key] = parse_value(value)
        except ValueError as error:
            raise ParseError(f".model {tokens[1]}: {key}: {error}") from None
    return Model(name, kind, params)


def _read_directive(line, where, circuit):
    tokens = tokenize(line)
    kind = tokens[0][1:].lower()
    positional, keywords = split_args([t.lower() for t in tokens[1:]])
    if kind == "temp":
        if not positional:
            raise ParseError("Usage: .temp <degrees C>")
        circuit.temperature = parse_value(positional[0])
    elif kind == "ic":
        found = re.findall(r"v\(\s*([^)\s]+)\s*\)\s*=\s*(\S+)", line, flags=re.I)
        if not found:
            raise ParseError("Usage: .ic v(<node>)=<volts> ...")
        for node, value in found:
            circuit.initial_conditions[normalize_node(node)] = parse_value(value)
    elif kind == "title":
        circuit.title = line[6:].strip()
    elif kind in ("end", "ends"):
        if kind == "ends":
            raise ParseError(".ends without a matching .subckt")
    elif kind in ANALYSES:
        circuit.directives.append(Directive(kind, positional, keywords, line, where))
    elif kind in IGNORED:
        circuit.warnings.append(f"{where}: .{kind} is not used by MiniSpice and was skipped")
    elif kind in ("include", "inc", "lib"):
        raise ParseError(f".{kind} could not be read (only .include <file> is supported)")
    else:
        raise ParseError(f"Unknown command .{kind}. Known commands: .op .dc .tran .ac .four .noise .step .mc .sens .temp .ic .model .subckt .param .include .end")


# ---- line handling ------------------------------------------------------------------------------


def _strip_comment(raw):
    line = raw.strip()
    if line.startswith("*"):
        return ""
    # Inline comments: ';' anywhere, or '$' after a space (ngspice style).
    line = line.split(";", 1)[0]
    line = re.split(r"\s\$", line, maxsplit=1)[0]
    return line.strip()


def _logical_lines(text, prefix, main=True):
    """Strip comments and join '+' continuation lines. Returns [(where, text)]."""
    out = []
    for number, raw in enumerate(text.splitlines(), 1):
        if main and number == 1 and raw.strip().startswith("*"):
            # A first-line comment doubles as the title, the way SPICE uses its first line.
            out.append((f"{prefix}line 1", "\x00title " + raw.strip()[1:].strip()))
            continue
        line = _strip_comment(raw)
        if not line:
            continue
        if line.startswith("+"):
            if out:
                out[-1] = (out[-1][0], out[-1][1] + " " + line[1:].strip())
            continue
        out.append((f"{prefix}line {number}", line))
    return out


def _take_title(lines, circuit):
    if not lines:
        return lines
    where, first = lines[0]
    if first.startswith("\x00title "):
        circuit.title = first[len("\x00title "):]
        return lines[1:]
    if where == "line 1" and not first.startswith(".") and _looks_like_title(first):
        circuit.title = first
        return lines[1:]
    return lines


def _looks_like_title(line):
    """SPICE files from other tools start with a title line, like 'RC low-pass filter'.

    A part name always has a digit or a short name and enough fields, and a title usually doesn't,
    so a first word without digits that doesn't parse as a part is taken as the title.
    """
    words = line.split()
    if any(ch.isdigit() for ch in words[0]):
        return False
    try:
        parse_element(line, {})
        return False
    except Exception:
        return True


def _skip_control_blocks(lines):
    out, skipping = [], False
    for where, line in lines:
        lower = line.lower()
        if lower.startswith(".control"):
            skipping = True
        elif lower.startswith(".endc"):
            skipping = False
        elif not skipping:
            out.append((where, line))
    return out


def _truncate_at_end(lines):
    for i, (_, line) in enumerate(lines):
        if line.lower().split()[0] == ".end":
            return lines[:i]
    return lines


def _expand_includes(lines, base_dir, problems, depth):
    out = []
    for where, line in lines:
        lower = line.lower()
        if lower.startswith((".include", ".inc ", ".lib ")):
            parts = line.split(None, 1)
            if len(parts) < 2:
                problems.append((where, ".include needs a file name"))
                continue
            name = parts[1].strip().strip("'\"")
            if lower.startswith(".lib ") and len(name.split()) > 1:
                problems.append((where, ".lib with a section name isn't supported; use .include"))
                continue
            path = name if os.path.isabs(name) or base_dir is None else os.path.join(base_dir, name)
            if depth > 10:
                problems.append((where, f".include nests more than 10 deep; is '{name}' including itself?"))
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
            except OSError:
                problems.append((where, f"can't open included file '{name}' (looked in {os.path.dirname(path) or '.'})"))
                continue
            included = _logical_lines(text, f"{os.path.basename(path)} ", main=False)
            out.extend(_expand_includes(included, os.path.dirname(path), problems, depth + 1))
        else:
            out.append((where, line))
    return out


# ---- parameters -----------------------------------------------------------------------------------

_FUNCTIONS = {
    "sqrt": math.sqrt, "exp": math.exp, "log": math.log, "ln": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "abs": abs, "min": min, "max": max, "pow": pow,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}


def _read_params(line, params):
    body = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ""
    body = re.sub(r"\s*=\s*", "=", body)
    assignments = re.findall(r"(\w+)=(\{[^}]*\}|\S+)", body)
    if not assignments:
        raise ParseError("Usage: .param <name>=<value> ...")
    for name, value in assignments:
        expr = value[1:-1] if value.startswith("{") else value
        params[name.lower()] = evaluate_expression(expr, params)


def substitute_params(line, params):
    """Replace {expressions} with their numbers, so the rest of the parser only sees plain values."""
    if "{" not in line:
        return line
    return re.sub(r"\{([^}]*)\}", lambda m: repr(evaluate_expression(m.group(1), params)), line)


def evaluate_expression(expr, params):
    """Safely evaluate arithmetic like '2*rbase + 1k'. Only numbers, parameters and math functions."""
    python = re.sub(
        r"(?<![\w.])(\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[a-zA-Zµ]*",
        lambda m: repr(parse_value(m.group(0))),
        expr,
    )
    try:
        tree = ast.parse(python.strip(), mode="eval")
    except SyntaxError:
        raise ParseError(f"can't read the expression '{{{expr}}}'") from None
    return float(_eval(tree.body, params, expr))


def _eval(node, params, expr):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name):
        name = node.id.lower()
        if name in params:
            return params[name]
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        raise ParseError(f"'{node.id}' in '{{{expr}}}' is not a defined .param")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _eval(node.operand, params, expr)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, params, expr), _eval(node.right, params, expr)
        ops = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right, ast.Mult: lambda: left * right,
               ast.Div: lambda: left / right, ast.Pow: lambda: left ** right}
        for op_type, fn in ops.items():
            if isinstance(node.op, op_type):
                try:
                    return fn()
                except ZeroDivisionError:
                    raise ParseError(f"division by zero in '{{{expr}}}'") from None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.lower() in _FUNCTIONS:
        return _FUNCTIONS[node.func.id.lower()](*[_eval(a, params, expr) for a in node.args])
    raise ParseError(f"'{{{expr}}}' uses something other than numbers, parameters and + - * / ** or math functions")
