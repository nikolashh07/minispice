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
        epilog=("Also: 'check FILE' checks homework answers, 'practice' gives practice problems, 'compare CIRCUIT CSV' "
                "compares with measurements, 'measure --port PORT' records a microcontroller, 'overlay' plots both. "
                "Example: python -m minispice practice"),
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
    analyses.add_argument("--sweep", nargs=4, metavar=("NAME", "START", "STOP", "STEP"), help="DC sweep of a source, a part's value, or temp")
    analyses.add_argument("--mc", type=int, metavar="RUNS", help="Monte Carlo: RUNS random builds within each part's tol=")
    analyses.add_argument("--worst-case", action="store_true", help="worst-case output with every toleranced part at an extreme")
    analyses.add_argument("--sens", metavar="EXPR", help="sensitivity of EXPR (like v(out)) to every part, ranked")
    analyses.add_argument("--noise", nargs="+", metavar="ARG", help="noise at OUTPUT [INPUT SOURCE], e.g. --noise v(out) VIN (frequencies from --ac or .ac)")

    options = parser.add_argument_group("options")
    options.add_argument("--remove", action="append", default=[], metavar="PART", help="remove a part (like a load) before a theorem analysis")
    options.add_argument("--temp", type=float, help="circuit temperature in °C (default 27, or .temp)")
    options.add_argument("--probe", action="append", default=[], metavar="EXPR", help="what to report: v(out), v(a,b), i(R1), p(R1). Repeatable")
    options.add_argument("--plot", nargs="?", const="output", metavar="DIR", help="save plots as PNG files (default folder: output)")
    options.add_argument("--method", choices=["be", "trap"], help="transient integration: backward Euler or trapezoidal (default)")
    options.add_argument("--fixed-step", action="store_true", help="transient: use a fixed time step instead of adaptive")
    options.add_argument("--step", nargs="+", metavar="ARG", help="rerun the analyses for several values: --step R1 1k 2k 5k")
    options.add_argument("--explain", nargs="?", const="-", metavar="FILE",
                         help="explain the DC solution step by step; FILE (.txt .md .tex .pdf) saves it instead of printing")
    options.add_argument("--schematic", metavar="FILE", help="draw the circuit, annotated with DC results, to FILE (.svg or .png)")
    options.add_argument("--plain-schematic", action="store_true", help="with --schematic: draw without results")
    options.add_argument("--seed", type=int, default=1, help="Monte Carlo random seed (default 1)")
    options.add_argument("--gaussian", action="store_true", help="Monte Carlo: normal distribution (tol = 3 sigma) instead of uniform")
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


def run_sweep(circuit, args):
    from .analysis.sweep import dc_from_directive, dc_sweep, sweep_values
    from .units import parse_value

    if args.sweep:
        name, start, stop, step = args.sweep
        result = dc_sweep(circuit, name, sweep_values(parse_value(start), parse_value(stop), parse_value(step)))
    else:
        result = dc_from_directive(circuit, circuit.find_directives("dc")[0])
    probes = _probes(circuit, args)
    unit = "°C" if result.name.lower() == "temp" else (circuit.get(result.name).unit if circuit.has(result.name) else "")
    print(heading(f"DC sweep of {result.name}"))
    curves = {p: result.measure(p) for p in probes}
    rows = [[format_eng(result.values[k], unit)] + [format_eng(curves[p][k], _unit_of(p)) for p in probes]
            for k in _sample_rows(len(result.values), 26)]
    print(table([result.name] + probes, rows))
    if args.plot:
        from .plotting import plot_sweep

        path = plot_sweep(result.values, curves, f"{args.plot}/sweep.png", f"{result.name} ({unit})", f"DC sweep of {result.name}")
        print(f"\nPlot saved to {path}")


def _first_probe(circuit, args, directive_kind):
    import re

    if args.probe:
        return args.probe[0]
    found = circuit.find_directives(directive_kind)
    if found:
        match = re.search(r"\w+\([^)]*\)", found[0].raw)
        if match:
            return match.group(0)
    raise MiniSpiceError(f"Say which output to measure with --probe, like --probe v(out)")


def run_mc(circuit, args):
    from .analysis.montecarlo import monte_carlo

    runs, seed, gaussian = args.mc, args.seed, args.gaussian
    if runs is None:
        directive = circuit.find_directives("mc")[0]
        runs = int(directive.args[0]) if directive.args and directive.args[0].isdigit() else 200
        seed = int(directive.keywords.get("seed", seed))
        gaussian = gaussian or directive.keywords.get("dist", "") == "gaussian"
    expr = _first_probe(circuit, args, "mc")
    result = monte_carlo(circuit, expr, runs, seed, "gaussian" if gaussian else "uniform")
    unit = _unit_of(expr)
    print(heading(f"Monte Carlo: {runs} random builds, {expr}"))
    print(table(["Statistic", "Value"], [
        ("nominal", format_eng(result.nominal, unit)),
        ("mean", format_eng(result.mean, unit)),
        ("standard deviation", format_eng(result.std, unit)),
        ("lowest", format_eng(result.low, unit)),
        ("highest", format_eng(result.high, unit)),
    ]))
    if args.plot:
        from .plotting import plot_histogram

        print(f"\nPlot saved to {plot_histogram(result.values, f'{args.plot}/montecarlo.png', expr, f'Monte Carlo ({runs} runs)')}")


def run_worst_case(circuit, args):
    from .analysis.montecarlo import worst_case

    expr = _first_probe(circuit, args, "mc")
    result = worst_case(circuit, expr)
    unit = _unit_of(expr)
    print(heading(f"Worst case of {expr} ({result.method})"))
    print(table(["", "Value", "Part values"], [
        ("lowest", format_eng(result.low, unit), ", ".join(f"{k}={v:.4g}" for k, v in result.low_corner.items())),
        ("nominal", format_eng(result.nominal, unit), ""),
        ("highest", format_eng(result.high, unit), ", ".join(f"{k}={v:.4g}" for k, v in result.high_corner.items())),
    ]))


def run_sens(circuit, args):
    from .analysis.sensitivity import sensitivity

    expr = args.sens or _first_probe(circuit, args, "sens")
    rows = []
    for s in sensitivity(circuit, expr):
        part_unit = circuit.get(s.name).unit
        rows.append((s.name, s.kind, format_eng(s.value, part_unit), f"{s.derivative:.4g}", f"{s.normalized:+.4f}"))
    print(heading(f"Sensitivity of {expr}, most influential first"))
    print(table(["Part", "Type", "Value", "d(output)/d(value)", "% per %"], rows))
    print("\n'% per %' is how many percent the output moves when the part changes by 1 %.")


def run_noise(circuit, args):
    from .analysis.noise import noise_analysis, noise_from_directive
    from .units import parse_value

    if args.noise:
        output = args.noise[0]
        source = args.noise[1] if len(args.noise) > 1 else None
        if args.ac and len(args.ac) == 4:
            sweep, points, f1, f2 = args.ac[0], parse_value(args.ac[1]), parse_value(args.ac[2]), parse_value(args.ac[3])
        elif circuit.find_directives("ac"):
            a = circuit.find_directives("ac")[0].args
            sweep, points, f1, f2 = a[0], parse_value(a[1]), parse_value(a[2]), parse_value(a[3])
        else:
            sweep, points, f1, f2 = "dec", 10, 1.0, 1e6
        result = noise_analysis(circuit, output, source, f1, f2, points, sweep)
    else:
        result = noise_from_directive(circuit, circuit.find_directives("noise")[0])
    print(heading(f"Noise at {result.output}"))
    headers = ["Frequency", "Output (V/√Hz)"] + (["Input-referred"] if result.gain is not None else [])
    rows = []
    for k in _sample_rows(len(result.freqs), 15):
        row = [format_eng(result.freqs[k], "Hz"), format_eng(result.output_density[k], "V")]
        if result.gain is not None:
            row.append(format_eng(result.input_density[k], "V"))
        rows.append(row)
    print(table(headers, rows))
    print(f"\nTotal output noise from {format_eng(result.freqs[0], 'Hz')} to {format_eng(result.freqs[-1], 'Hz')}: "
          f"{format_eng(result.total_rms(), 'V')} rms")
    print(table(["Part", "Share of noise power"], [(n, f"{share * 100:.1f} %") for n, share in result.ranked_contributors()[:8]]))
    if args.plot:
        from .plotting import plot_noise

        print(f"\nPlot saved to {plot_noise(result.freqs, result.output_density, f'{args.plot}/noise.png')}")


def run_explain(circuit, args):
    from .explain import explain_dc

    walkthrough, _ = explain_dc(circuit)
    if args.explain == "-":
        print()
        print(walkthrough.to_text())
    else:
        print(f"Explanation saved to {walkthrough.save(args.explain)}")


def run_schematic(circuit, args):
    from .schematic import draw_schematic

    solution = None if args.plain_schematic else operating_point(circuit)
    draw_schematic(circuit, args.schematic, solution)
    print(f"Schematic saved to {args.schematic}")


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
    ("sweep", run_sweep),
    ("mc", run_mc),
    ("worst_case", run_worst_case),
    ("sens", run_sens),
    ("noise", run_noise),
    ("explain", run_explain),
    ("schematic", run_schematic),
]

# Netlist dot-commands that map to a handler, for when no analysis option is given.
DIRECTIVE_HANDLERS = {
    "op": run_op, "tran": run_tran, "ac": run_ac, "four": run_four,
    "dc": run_sweep, "mc": run_mc, "sens": run_sens, "noise": run_noise,
}


def _step_plan(circuit, args):
    """(part name, values) from --step or .step, or None."""
    from .analysis.sweep import step_values
    from .units import parse_value

    if args.step:
        if len(args.step) < 2:
            raise MiniSpiceError("--step needs a part and at least one value: --step R1 1k 2k 5k")
        return args.step[0], [parse_value(v) for v in args.step[1:]]
    found = circuit.find_directives("step")
    if found:
        return step_values(found[0].args)
    return None


# ---- subcommands ---------------------------------------------------------------------------------


def check_main(argv):
    """python -m minispice check homework.cir"""
    from .homework import check_answers, read_answers

    parser = argparse.ArgumentParser(prog="python -m minispice check", description="Check your answers to a circuit problem.")
    parser.add_argument("netlist", help="circuit file with '* answer: v(2) = 5' lines")
    parser.add_argument("--tol", default="2%", help="how close counts as right (default 2%%)")
    args = parser.parse_args(argv)
    from .units import parse_value

    with open(args.netlist, encoding="utf-8") as handle:
        text = handle.read()
    report = check_answers(load(args.netlist), read_answers(text), parse_value(args.tol))
    print(report.to_text())
    return 0 if report.all_correct else 3


def practice_main(argv):
    """python -m minispice practice [--level N] [--seed S]: solve random circuits by hand."""
    from .homework import check_answers, generate_problem
    from .netlist import parse
    from .units import parse_value

    parser = argparse.ArgumentParser(prog="python -m minispice practice", description="Practice solving circuits by hand.")
    parser.add_argument("--level", type=int, default=1, choices=[1, 2, 3, 4], help="1 divider, 2 series-parallel, 3 two sources, 4 current source")
    parser.add_argument("--seed", type=int, help="pick a specific problem")
    parser.add_argument("--schematic", metavar="FILE", help="also draw the circuit to FILE")
    args = parser.parse_args(argv)
    problem = generate_problem(args.seed, args.level)
    circuit = parse(problem.netlist)
    print(problem.netlist)
    if args.schematic:
        from .schematic import draw_schematic

        draw_schematic(circuit, args.schematic)
        print(f"(drawing saved to {args.schematic})")
    print("Answer with units if you like: 4.5, 4.5V, 2m, 2mA. Currents use the passive sign convention.")
    answers = []
    for question in problem.questions:
        while True:
            reply = input(f"{question} = ").strip()
            try:
                answers.append((question, parse_value(reply)))
                break
            except ValueError:
                print("  That isn't a number. Try something like 4.5 or 2m.")
    report = check_answers(circuit, answers)
    print()
    print(report.to_text())
    if not report.all_correct:
        from .explain import explain_dc

        print("\nHere is the full solution:\n")
        print(explain_dc(circuit)[0].to_text())
    return 0 if report.all_correct else 3


def compare_main(argv):
    """python -m minispice compare circuit.cir readings.csv: simulation vs your multimeter."""
    from .hardware import compare, comparison_table, read_measurements

    parser = argparse.ArgumentParser(prog="python -m minispice compare", description="Compare simulated values with measurements.")
    parser.add_argument("netlist")
    parser.add_argument("measurements", help="CSV with columns probe,measured (like v(2),4.93)")
    parser.add_argument("--meter-resistance", default="10meg", help="your voltmeter's input resistance (default 10meg)")
    args = parser.parse_args(argv)
    from .units import parse_value

    rows = compare(load(args.netlist), read_measurements(args.measurements), parse_value(args.meter_resistance))
    print(comparison_table(rows))
    return 0


def measure_main(argv):
    """python -m minispice measure --port COM3: record samples from the MiniSpice probe firmware."""
    from .hardware import HardwareLink, write_samples

    parser = argparse.ArgumentParser(prog="python -m minispice measure", description="Record voltages from a microcontroller.")
    parser.add_argument("--port", required=True, help="serial port, like COM3 or /dev/ttyACM0")
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--out", default="samples.csv")
    parser.add_argument("--vref", type=float, default=5.0, help="ADC reference: 5 for an Arduino Uno, 3.3 for an ESP32")
    parser.add_argument("--bits", type=int, default=10, help="ADC resolution: 10 for an Uno, 12 for an ESP32")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args(argv)
    link = HardwareLink(args.port, args.baud, args.vref, args.bits)
    try:
        count = write_samples(args.out, link.samples(args.seconds))
    finally:
        link.close()
    print(f"Saved {count} samples to {args.out}")
    return 0


def overlay_main(argv):
    """python -m minispice overlay circuit.cir samples.csv --probe v(out) --channel a0"""
    from .analysis.transient import TransientSettings, run_settings, settings_from_directive
    from .hardware import read_samples
    from .plotting import plot_overlay
    from .units import parse_value

    parser = argparse.ArgumentParser(prog="python -m minispice overlay", description="Plot measured samples on top of the simulation.")
    parser.add_argument("netlist")
    parser.add_argument("samples", help="CSV from 'python -m minispice measure'")
    parser.add_argument("--probe", required=True, help="simulated quantity, like v(out)")
    parser.add_argument("--channel", default="a0", help="measured column: a0, a1, ...")
    parser.add_argument("--out", default="output/overlay.png")
    args = parser.parse_args(argv)
    circuit = load(args.netlist)
    times, channels = read_samples(args.samples)
    if args.channel not in channels:
        raise MiniSpiceError(f"{args.samples} has no column {args.channel}; it has {', '.join(channels)}")
    found = circuit.find_directives("tran")
    if found:
        settings = settings_from_directive(found[0])
    else:
        settings = TransientSettings(t_stop=max(times), t_step=max(times) / 500)
    result = run_settings(circuit, settings)
    path = plot_overlay(result.times, result.measure(args.probe), times, channels[args.channel], args.out, args.probe)
    print(f"Plot saved to {path}")
    return 0


SUBCOMMANDS = {"check": check_main, "practice": practice_main, "compare": compare_main, "measure": measure_main, "overlay": overlay_main}


def main(argv=None):
    # Windows consoles default to a code page without Ω and µ.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in SUBCOMMANDS:
        try:
            return SUBCOMMANDS[argv[0]](argv[1:])
        except FileNotFoundError as error:
            print(f"error: can't open '{error.filename}'", file=sys.stderr)
            return 2
        except MiniSpiceError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
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
        steps = _step_plan(circuit, args)
        if steps is None:
            for handler in chosen:
                handler(circuit, args)
        else:
            from .analysis.sweep import set_value

            name, values = steps
            for value in values:
                work = circuit.copy()
                set_value(work, name, value)
                unit = work.get(name).unit if name.lower() != "temp" else "°C"
                print(f"\n########## {name} = {format_eng(value, unit)} ##########")
                args._tran_result = None
                for handler in chosen:
                    handler(work, args)
    except FileNotFoundError as error:
        print(f"error: can't open '{error.filename}'", file=sys.stderr)
        return 2
    except MiniSpiceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
