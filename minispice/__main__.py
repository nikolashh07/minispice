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
    analyses.add_argument("--tran", nargs="*", metavar="TIME", help="transient: --tran TSTEP TSTOP (or use the netlist's .tran)")
    analyses.add_argument("--ac", nargs="*", metavar="ARG", help="AC sweep: --ac dec POINTS FSTART FSTOP (or use the netlist's .ac)")
    analyses.add_argument("--four", type=str, metavar="FREQ", help="Fourier analysis of the transient result at fundamental FREQ")

    options = parser.add_argument_group("options")
    options.add_argument("--remove", action="append", default=[], metavar="PART", help="remove a part (like a load) before a theorem analysis")
    options.add_argument("--temp", type=float, help="circuit temperature in °C (default 27, or .temp)")
    options.add_argument("--probe", action="append", default=[], metavar="EXPR", help="what to report: v(out), v(a,b), i(R1), p(R1). Repeatable")
    options.add_argument("--plot", nargs="?", const="output", metavar="DIR", help="save plots as PNG files (default folder: output)")
    options.add_argument("--method", choices=["be", "trap"], help="transient integration: backward Euler or trapezoidal (default)")
    options.add_argument("--fixed-step", action="store_true", help="transient: use a fixed time step instead of adaptive")
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


def _probes(circuit, args, default_kind="v"):
    if args.probe:
        return args.probe
    nodes = [n for n in circuit.nodes if "." not in n and "#" not in n]
    return [f"{default_kind}({n})" for n in nodes[:6]]


def _unit_of(expr):
    return {"v": "V", "i": "A", "p": "W"}.get(expr.strip().lower()[:1], "")


def _sample_rows(count, limit=21):
    """Indices of at most `limit` evenly spread rows, always including the first and last."""
    import numpy as np

    if count <= limit:
        return list(range(count))
    return sorted(set(np.linspace(0, count - 1, limit).round().astype(int)))


def _transient(circuit, args):
    """Run (or reuse) the transient described by --tran or the netlist's .tran."""
    from .analysis.transient import TransientSettings, run_settings, settings_from_directive
    from .units import parse_value

    if getattr(args, "_tran_result", None) is not None:
        return args._tran_result
    if args.tran:
        if len(args.tran) != 2:
            raise MiniSpiceError("--tran needs two values: TSTEP TSTOP (for example --tran 10u 5m)")
        settings = TransientSettings(t_step=parse_value(args.tran[0]), t_stop=parse_value(args.tran[1]))
    else:
        found = circuit.find_directives("tran")
        if not found:
            raise MiniSpiceError("No transient settings: add '.tran <tstep> <tstop>' to the netlist or use --tran TSTEP TSTOP")
        settings = settings_from_directive(found[0])
    if args.method:
        settings.method = args.method
    if args.fixed_step:
        settings.adaptive = False
    args._tran_settings = settings
    args._tran_result = run_settings(circuit, settings)
    return args._tran_result


def run_tran(circuit, args):
    result = _transient(circuit, args)
    probes = _probes(circuit, args)
    settings = args._tran_settings
    print(heading(f"Transient analysis to {format_eng(settings.t_stop, 's')} ({settings.method}, "
                  f"{'adaptive' if settings.adaptive else 'fixed'} step, {len(result.times)} time points)"))
    grid_values = [result.uniform(p, settings.t_step) for p in probes]
    grid = grid_values[0][0]
    rows = []
    for k in _sample_rows(len(grid)):
        rows.append([format_eng(grid[k], "s")] + [format_eng(values[k], _unit_of(p)) for p, (_, values) in zip(probes, grid_values)])
    print(table(["Time"] + probes, rows))
    if args.plot:
        from .plotting import plot_transient

        path = plot_transient(result, probes, f"{args.plot}/transient.png", circuit.title or "Transient analysis")
        print(f"\nPlot saved to {path}")


def run_ac(circuit, args):
    from .analysis.ac import ac_analysis, ac_from_directive, db, phase_degrees
    from .units import parse_value

    if args.ac:
        if len(args.ac) != 4:
            raise MiniSpiceError("--ac needs four values: dec|oct|lin POINTS FSTART FSTOP (for example --ac dec 10 1 1meg)")
        sweep, points, f1, f2 = args.ac
        result = ac_analysis(circuit, parse_value(f1), parse_value(f2), parse_value(points), sweep)
    else:
        found = circuit.find_directives("ac")
        if not found:
            raise MiniSpiceError("No AC settings: add '.ac dec <points> <fstart> <fstop>' or use --ac dec 10 1 1meg")
        result = ac_from_directive(circuit, found[0])
    probes = _probes(circuit, args)
    print(heading(f"AC analysis, {format_eng(result.freqs[0], 'Hz')} to {format_eng(result.freqs[-1], 'Hz')}"))
    headers = ["Frequency"]
    for p in probes:
        headers += [f"|{p}| dB", f"{p} phase"]
    mags = {p: db(result.measure(p)) for p in probes}
    phases = {p: phase_degrees(result.measure(p)) for p in probes}
    rows = []
    for k in _sample_rows(len(result.freqs)):
        row = [format_eng(result.freqs[k], "Hz")]
        for p in probes:
            row += [f"{mags[p][k]:.2f}", f"{phases[p][k]:.1f}°"]
        rows.append(row)
    print(table(headers, rows))
    for p in probes:
        corner = result.corner_frequency(p)
        if corner:
            print(f"{p} is 3 dB below its low-frequency level at {format_eng(corner, 'Hz')}")
    if args.plot:
        from .plotting import plot_bode

        for n, p in enumerate(probes):
            print(f"Plot saved to {plot_bode(result, p, f'{args.plot}/bode_{n + 1}.png')}")


def run_four(circuit, args):
    import re

    from .analysis.fourier import fourier
    from .units import parse_value

    if args.four:
        freq = parse_value(args.four)
        probes = _probes(circuit, args)
    else:
        directive = circuit.find_directives("four")[0]
        if not directive.args:
            raise MiniSpiceError("Usage: .four <fundamental frequency> v(node) ...")
        freq = parse_value(directive.args[0])
        probes = re.findall(r"\w+\([^)]*\)", directive.raw) or _probes(circuit, args)
    result = _transient(circuit, args)
    for p in probes:
        f = fourier(result.times, result.measure(p), freq)
        print(heading(f"Fourier analysis of {p} (fundamental {format_eng(freq, 'Hz')})"))
        print(f"DC component: {format_eng(f.dc, _unit_of(p))}")
        rows = [(int(h), format_eng(fr, "Hz"), format_eng(m, _unit_of(p)), f"{n:.4f}", f"{ph:.1f}°")
                for h, fr, m, n, ph in zip(f.harmonics, f.frequencies, f.magnitudes, f.normalized(), f.phases)]
        print(table(["Harmonic", "Frequency", "Amplitude", "Relative", "Phase"], rows))
        print(f"Total harmonic distortion: {f.thd * 100:.3f} %")
        if args.plot:
            from .plotting import plot_harmonics

            print(f"Plot saved to {plot_harmonics(f, f'{args.plot}/harmonics.png', f'Harmonics of {p}')}")


# (option name, handler). Order is the order results are printed.
HANDLERS = [
    ("op", run_op),
    ("thevenin", run_thevenin),
    ("norton", run_norton),
    ("max_power", run_max_power),
    ("superposition", run_superposition),
    ("tran", run_tran),
    ("ac", run_ac),
    ("four", run_four),
]

# Netlist dot-commands that map to a handler, for when no analysis option is given.
DIRECTIVE_HANDLERS = {"op": run_op, "tran": run_tran, "ac": run_ac, "four": run_four}


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
        # "--tran" with no values still means "run the transient", so test against None.
        chosen = [handler for name, handler in HANDLERS if getattr(args, name) not in (None, False)]
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
