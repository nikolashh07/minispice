"""Plain-text tables for the command line."""

from .power import power_report
from .units import format_eng


def table(headers, rows):
    """Align columns with two spaces between them. Numbers should already be formatted as text."""
    rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip()]
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        lines.append("  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip())
    return "\n".join(lines)


def heading(text):
    return f"\n{text}\n{'=' * len(text)}"


def op_report(solution):
    out = [heading("DC operating point")]
    if solution.iterations > 1:
        out.append(f"(Newton's method converged in {solution.iterations} iterations)")
    voltages = solution.node_voltages
    out.append(table(["Node", "Voltage"], [(n, format_eng(v, "V")) for n, v in voltages.items()]))

    rows = []
    for name, kind, v, i, p, region in solution.component_rows():
        rows.append((name, kind + (f" ({region})" if region else ""), format_eng(v, "V"), format_eng(i, "A"), format_eng(p, "W")))
    out.append("")
    out.append(table(["Part", "Type", "Voltage", "Current", "Power absorbed"], rows))

    report = power_report(solution)
    out.append("")
    out.append(report.summary())
    for warning in report.warnings:
        out.append("WARNING: " + warning)
    return "\n".join(out)
