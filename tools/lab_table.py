"""Build the simulation-vs-reality table for docs/lab.md: python tools/lab_table.py

For every lab circuit in examples/lab with a measurement sheet (.csv), it lists the simulated value,
the range the part tolerances allow, what a 10 MΩ voltmeter should read, and the measured value
(blank until you fill in the sheet). Run it again after measuring to update the table.
"""

import csv
import os
import pathlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from minispice import load  # noqa: E402
from minispice.hardware import compare  # noqa: E402
from minispice.units import format_eng, parse_value  # noqa: E402

LAB = pathlib.Path(__file__).resolve().parent.parent / "examples" / "lab"
DOC = pathlib.Path(__file__).resolve().parent.parent / "docs" / "lab.md"
START, END = "<!-- lab-table:start -->", "<!-- lab-table:end -->"


def sheet_rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return [(row["probe"].strip(), (row.get("measured") or "").strip()) for row in csv.DictReader(handle) if row.get("probe")]


def build():
    lines = ["| Circuit | Quantity | Simulated | Tolerance range | With a 10 MΩ meter | Measured | Difference |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for sheet in sorted(LAB.glob("*.csv")):
        circuit_path = sheet.with_suffix(".cir")
        if not circuit_path.exists():
            continue
        circuit = load(str(circuit_path))
        rows = sheet_rows(sheet)
        # compare() needs a number for each probe; use 0 as a stand-in for readings not taken yet.
        results = compare(circuit, [(probe, parse_value(measured) if measured else 0.0) for probe, measured in rows])
        for (probe, measured), r in zip(rows, results):
            unit = {"v": "V", "i": "A", "p": "W"}.get(probe[0].lower(), "")
            span = f"{format_eng(r.low, unit)} to {format_eng(r.high, unit)}" if r.low is not None else "-"
            loaded = format_eng(r.loaded, unit) if r.loaded is not None else "-"
            shown = format_eng(r.measured, unit) if measured else ""
            diff = f"{r.error_percent:+.1f} %" if measured else ""
            lines.append(f"| {circuit_path.stem} | {probe} | {format_eng(r.simulated, unit)} | {span} | {loaded} | {shown} | {diff} |")
    return "\n".join(lines)


def main():
    table = build()
    text = DOC.read_text(encoding="utf-8")
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    DOC.write_text(before + START + "\n" + table + "\n" + END + after, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
