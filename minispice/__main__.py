"""Command line: python -m minispice <netlist> [analyses] [options]

Each analysis is one handler function plus one command-line option, so new analyses plug in
without touching the others. With no analysis options, MiniSpice runs whatever the netlist's
dot-commands ask for (.op, .tran, .ac, ...), or a DC operating point if there are none.
"""

import argparse
import sys

from . import __version__
from .analysis.dc import operating_point
from .errors import MiniSpiceError
from .netlist import load
from .report import heading, op_report, table
from .units import format_eng


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m minispice",
        description="MiniSpice circuit simulator. Example: python -m minispice examples/divider.cir --dc",
    )
    parser.add_argument("netlist", help="circuit file (.cir)")
    parser.add_argument("--version", action="version", version=f"MiniSpice {__version__}")

    analyses = parser.add_argument_group("analyses")
    analyses.add_argument("--dc", "--op", dest="op", action="store_true", help="DC operating point: node voltages, currents, power")
    analyses.add_argument("--thevenin", nargs="+", metavar="NODE", help="Thevenin equivalent between NODE A and NODE B (default ground)")
    analyses.add_argument("--norton", nargs="+", metavar="NODE", help="Norton equivalent between NODE A and NODE B (default ground)")
    analyses.add_argument("--max-power", nargs="+", metavar="NODE", help="best load resistance between NODE A and B, and its power")
    analyses.add_argument("--superposition", action="store_true", help="contribution of each independent source to every node")

    options = parser.add_argument_group("options")
    options.add_argument("--remove", action="append", default=[], metavar="PART", help="remove a part (like a load) before a theorem analysis")
    options.add_argument("--temp", type=float, help="circuit temperature in °C (default 27, or .temp)")
    return parser


# ---- handlers -----------------------------------------------------------------------------------


def run_op(circuit, args):
    print(op_report(operating_point(circuit)))


def _two_nodes(values):
    if len(values) > 2:
        raise MiniSpiceError("give one or two node names")
    return values[0], values[1] if len(values) > 1 else "0"


def run_thevenin(circuit, args):
    from .theorems import thevenin

    a, b = _two_nodes(args.thevenin)
    th = thevenin(circuit, a, b, args.remove)
    print(heading(f"Thevenin equivalent between {th.a} and {th.b}"))
    print(table(["Quantity", "Value"], [("Vth", format_eng(th.vth, "V")), ("Rth", format_eng(th.rth, "Ω"))]))


def run_norton(circuit, args):
    from .theorems import thevenin

    a, b = _two_nodes(args.norton)
    th = thevenin(circuit, a, b, args.remove)
    print(heading(f"Norton equivalent between {th.a} and {th.b}"))
    print(table(["Quantity", "Value"], [("In (from a to b)", format_eng(th.norton_current, "A")), ("Rn", format_eng(th.rth, "Ω"))]))


def run_max_power(circuit, args):
    from .theorems import max_power_transfer

    a, b = _two_nodes(args.max_power)
    rl, pmax, th = max_power_transfer(circuit, a, b, args.remove)
    print(heading(f"Maximum power transfer between {th.a} and {th.b}"))
    print(table(["Quantity", "Value"], [
        ("Vth", format_eng(th.vth, "V")),
        ("Rth", format_eng(th.rth, "Ω")),
        ("Best load RL = Rth", format_eng(rl, "Ω")),
        ("Maximum power Vth²/(4 Rth)", format_eng(pmax, "W")),
    ]))


def run_superposition(circuit, args):
    from .theorems import superposition

    result = superposition(circuit)
    names = list(result.parts)
    print(heading("Superposition: node voltages, one source at a time"))
    rows = []
    for node, (total, parts) in result.node_breakdown().items():
        rows.append([node] + [format_eng(parts[n], "V") for n in names] + [format_eng(total, "V")])
    print(table(["Node"] + [f"{n} only" for n in names] + ["All sources"], rows))
    print(f"\nLargest difference between the sum of the parts and the full solution: {result.max_error():.3g}")


# (option name, handler). Order is the order results are printed.
HANDLERS = [
    ("op", run_op),
    ("thevenin", run_thevenin),
    ("norton", run_norton),
    ("max_power", run_max_power),
    ("superposition", run_superposition),
]

# Netlist dot-commands that map to a handler, for when no analysis option is given.
DIRECTIVE_HANDLERS = {"op": run_op}


def main(argv=None):
    # Windows consoles default to a code page without Ω and µ.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        circuit = load(args.netlist)
        if args.temp is not None:
            circuit.temperature = args.temp
        if circuit.title:
            print(circuit.title)
        for warning in circuit.warnings:
            print("note: " + warning)
        chosen = [handler for name, handler in HANDLERS if getattr(args, name)]
        if not chosen:
            kinds = []
            for d in circuit.directives:
                if d.kind in DIRECTIVE_HANDLERS and DIRECTIVE_HANDLERS[d.kind] not in kinds:
                    kinds.append(DIRECTIVE_HANDLERS[d.kind])
            chosen = kinds or [run_op]
        for handler in chosen:
            handler(circuit, args)
    except FileNotFoundError as error:
        print(f"error: can't open '{error.filename}'", file=sys.stderr)
        return 2
    except MiniSpiceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
