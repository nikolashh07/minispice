"""Phase 23: run the example circuits through ngspice and MiniSpice and compare the answers.

    python tools/compare_ngspice.py          prints a table and writes docs/ngspice_validation.md

Needs ngspice on the PATH (free: https://ngspice.sourceforge.io). Examples that use MiniSpice-only
parts (the T ideal transformer, time-controlled S switches, U op-amps, STEP sources) are skipped,
and built-in MiniSpice models are written out as ordinary .model lines so ngspice sees the same devices.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from minispice import load, operating_point  # noqa: E402
from minispice.components.models import BUILTIN_MODELS  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
UNSUPPORTED_LETTERS = {"T", "S", "U"}
NGSPICE_NAMES = ("ngspice_con", "ngspice")


def find_ngspice():
    for name in NGSPICE_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def compatible(circuit):
    for comp in circuit.components:
        if comp.letter in UNSUPPORTED_LETTERS:
            return False
        waveform = getattr(comp, "waveform", None)
        if waveform is not None and waveform.name == "step":
            return False
    return True


def _model_line(model):
    params = dict(model.params)
    if model.type in ("nmos", "pmos"):
        params.setdefault("level", 1)
        params.setdefault("vto", 1.0 if model.type == "nmos" else -1.0)
        params.setdefault("kp", 2e-5)
    text = " ".join(f"{k.upper()}={v:g}" for k, v in params.items())
    return f".model {model.name} {model.type.upper()}({text})"


def ngspice_netlist(circuit):
    lines = [f"* {circuit.title or 'MiniSpice comparison'}"]
    used = {getattr(c, "model", None).name for c in circuit.components if getattr(c, "model", None) is not None}
    for name in sorted(used):
        model = circuit.models.get(name) or BUILTIN_MODELS[name]
        lines.append(_model_line(model))
    for comp in circuit.components:
        lines.append(comp.netlist_line())
    if circuit.temperature != 27.0:
        lines.append(f".temp {circuit.temperature:g}")
    lines += [".control", "op", "print all", ".endc", ".end"]
    return "\n".join(lines) + "\n"


def run_ngspice(executable, netlist):
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "circuit.cir")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(netlist)
        done = subprocess.run([executable, "-b", path], capture_output=True, text=True, timeout=60)
    values = {}
    for line in (done.stdout + done.stderr).splitlines():
        match = re.match(r"^\s*(?:v\()?([\w.#]+)\)?\s*=\s*([-+0-9.eE]+)\s*$", line.strip(), re.I)
        if match:
            values[match.group(1).lower()] = float(match.group(2))
    return values


def compare(executable):
    rows = []
    for name in sorted(os.listdir(os.path.join(ROOT, "examples"))):
        if not name.endswith(".cir"):
            continue
        circuit = load(os.path.join(ROOT, "examples", name))
        if not compatible(circuit) or not circuit.find_directives("op"):
            continue
        ours = operating_point(circuit).node_voltages
        theirs = run_ngspice(executable, ngspice_netlist(circuit))
        for node, value in ours.items():
            if node in theirs:
                rows.append((name, node, value, theirs[node], abs(value - theirs[node])))
    return rows


def table(rows):
    lines = ["| Example | Node | MiniSpice | ngspice | Difference |", "|---|---|---:|---:|---:|"]
    for name, node, ours, theirs, diff in rows:
        lines.append(f"| {name} | {node} | {ours:.6g} V | {theirs:.6g} V | {diff:.1e} V |")
    return "\n".join(lines)


def main():
    executable = find_ngspice()
    if executable is None:
        print("ngspice was not found on the PATH. Install it from https://ngspice.sourceforge.io and try again.")
        return 1
    rows = compare(executable)
    text = table(rows)
    print(text)
    worst = max((r[4] for r in rows), default=0.0)
    out = os.path.join(ROOT, "docs", "ngspice_validation.md")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write("# Validation against ngspice\n\nDC operating points of the example circuits, from "
                     "`python tools/compare_ngspice.py`.\n\n" + text + f"\n\nLargest difference: {worst:.1e} V\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
