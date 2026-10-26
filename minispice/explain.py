"""Explain mode: records which law each solver step used, in plain English.

Every stamp can leave a short note on a Recorder ("Ohm's law: R1 adds 1 mS at nodes 1 and 2").
explain_dc() turns those notes, plus the equations and the answer, into a step-by-step walkthrough
that reads like a tutor solving the problem, and Walkthrough.save() exports it as text, Markdown,
LaTeX or PDF.
"""

from dataclasses import dataclass, field

import numpy as np

from .units import format_eng


@dataclass
class Note:
    law: str
    text: str
    parts: tuple = ()  # names of the parts involved, so the browser can highlight them


@dataclass
class Recorder:
    notes: list = field(default_factory=list)
    unknowns: list = None
    matrix: object = None
    rhs: object = None
    solution: object = None
    iterations: int = 0

    def note(self, law, text, parts=()):
        self.notes.append(Note(law, text, tuple(parts)))

    def capture(self, layout, system, x, iterations):
        self.unknowns = layout.unknown_names()
        self.matrix = system.dense()
        self.rhs = system.b.copy()
        self.solution = x.copy()
        self.iterations = iterations


# ---- walkthroughs -------------------------------------------------------------------------------


@dataclass
class Step:
    title: str
    law: str
    lines: list
    parts: tuple = ()  # parts to highlight while this step is shown
    latex: list = field(default_factory=list)  # equations for the LaTeX export


@dataclass
class Walkthrough:
    title: str
    steps: list

    def to_text(self):
        out = [self.title, "=" * len(self.title)]
        for n, step in enumerate(self.steps, 1):
            out.append("")
            out.append(f"Step {n}: {step.title}  [{step.law}]")
            out.extend("  " + line for line in step.lines)
        return "\n".join(out) + "\n"

    def to_markdown(self):
        out = [f"# {self.title}"]
        for n, step in enumerate(self.steps, 1):
            out.append(f"\n## Step {n}: {step.title}\n\n*{step.law}*\n")
            out.extend(_markdown_line(line) for line in step.lines)
        return "\n".join(out) + "\n"

    def to_latex(self):
        out = [
            r"\documentclass[11pt]{article}",
            r"\usepackage[margin=1in]{geometry}",
            r"\usepackage{amsmath,amssymb}",
            r"\begin{document}",
            r"\section*{" + _tex_escape(self.title) + "}",
        ]
        for n, step in enumerate(self.steps, 1):
            out.append(r"\subsection*{Step " + str(n) + ": " + _tex_escape(step.title) + "}")
            out.append(r"\textit{" + _tex_escape(step.law) + r"}\par")
            for line in step.lines:
                out.append(_tex_escape(line.strip()) + r"\par")
            for equation in step.latex:
                out.append(r"\[ " + equation + r" \]")
        out.append(r"\end{document}")
        return "\n".join(out) + "\n"

    def to_dict(self):
        return {"title": self.title, "steps": [
            {"title": s.title, "law": s.law, "lines": list(s.lines), "parts": list(s.parts)} for s in self.steps
        ]}

    def save(self, path):
        """Write .txt, .md, .tex or .pdf, chosen by the file extension."""
        lower = path.lower()
        if lower.endswith(".pdf"):
            return _save_pdf(self, path)
        if lower.endswith(".tex"):
            text = self.to_latex()
        elif lower.endswith(".md"):
            text = self.to_markdown()
        else:
            text = self.to_text()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


def _markdown_line(line):
    # Indented lines are equations: keep them as a code block line; others become paragraphs.
    return line if line.startswith("    ") else line + "\n"


_TEX = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\^{}", "Ω": r"$\Omega$",
        "µ": r"$\mu$", "−": "-", "×": r"$\times$", "²": r"$^2$", "✓": r"$\checkmark$", "✗": r"$\times$",
        "°": r"$^\circ$", "≈": r"$\approx$", "Σ": r"$\Sigma$", "·": r"$\cdot$"}


def _tex_escape(text):
    return "".join(_TEX.get(ch, ch) for ch in text)


def _save_pdf(walkthrough, path):
    """A plain, readable PDF drawn with matplotlib, so no LaTeX installation is needed."""
    import textwrap

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    lines = [("title", walkthrough.title)]
    for n, step in enumerate(walkthrough.steps, 1):
        lines.append(("gap", ""))
        lines.append(("step", f"Step {n}: {step.title}"))
        lines.append(("law", step.law))
        for line in step.lines:
            mono = line.startswith("    ")
            for piece in textwrap.wrap(line, 100 if mono else 92, subsequent_indent="      " if mono else "") or [""]:
                lines.append(("mono" if mono else "body", piece))
    styles = {
        "title": dict(fontsize=15, weight="bold"), "step": dict(fontsize=12, weight="bold"),
        "law": dict(fontsize=9, style="italic", color="#555555"), "body": dict(fontsize=9.5),
        "mono": dict(fontsize=8.5, family="monospace"), "gap": dict(fontsize=6),
    }
    heights = {"title": 0.04, "step": 0.03, "law": 0.022, "body": 0.02, "mono": 0.019, "gap": 0.012}
    with PdfPages(path) as pdf:
        fig, y = None, 0.0
        for kind, text in lines:
            if fig is None or y - heights[kind] < 0.05:
                if fig is not None:
                    pdf.savefig(fig)
                    plt.close(fig)
                fig = plt.figure(figsize=(8.5, 11))
                y = 0.95
            # Dollar signs would switch matplotlib into math mode.
            fig.text(0.07, y, text.replace("$", r"\$"), va="top", **styles[kind])
            y -= heights[kind]
        if fig is not None:
            pdf.savefig(fig)
            plt.close(fig)
    return path


def _v(node):
    return "0" if node == "0" else f"V({node})"


def _vtex(node):
    return "0" if node == "0" else f"V_{{{node}}}"


def _kcl_term(comp, node, solution):
    """How a part's current leaving `node` appears in KCL: (text, latex, amps at the answer)."""
    current = 0.0
    for n, i in zip(comp.nodes, comp.terminal_currents(solution.x, solution.ctx)):
        if n == node:
            current += float(i)
    others = [n for n in comp.nodes if n != node]
    letter = comp.letter
    if letter == "R":
        other = others[0] if others else node
        r = format_eng(comp.value, "Ω")
        return f"({_v(node)} − {_v(other)}) / {r}", rf"\frac{{{_vtex(node)} - {_vtex(other)}}}{{{_tex_escape(r)}}}", current
    if letter == "C":
        return f"0 (capacitor {comp.name} is open at DC)", "0", current
    if letter in ("V", "L", "E", "H", "U", "T"):
        sign = "" if (comp.nodes[0] == node or letter == "U") else "−"
        return f"{sign}I({comp.name})", f"{sign}I_{{{comp.name}}}", current
    if letter == "I":
        value = format_eng(comp.value, "A")
        sign = "" if comp.nodes[0] == node else "−"
        return f"{sign}{value} (source {comp.name})", f"{sign}{_tex_escape(value)}", current
    return f"I_{comp.name}", f"I_{{{comp.name}}}", current


def _join(terms):
    return " + ".join(terms).replace("+ −", "− ").replace("+ -", "− ")


def explain_dc(circuit):
    """A tutor-style walkthrough of the DC operating point. Returns (Walkthrough, Solution)."""
    from .analysis.dc import operating_point
    from .power import power_report

    recorder = Recorder()
    solution = operating_point(circuit, recorder=recorder)
    layout = solution.layout
    nodes = [n for n in layout.nodes if "#" not in n]
    branch_parts = [c for c in circuit.components if c.n_branches]
    steps = []

    # 1. Unknowns.
    lines = ["Node 0 is ground: the 0 V reference every other voltage is measured from.",
             f"The unknown node voltages are {', '.join(_v(n) for n in nodes)}."]
    if branch_parts:
        lines.append(
            f"{', '.join(c.name for c in branch_parts)} fix a voltage instead of a current, so the currents "
            f"{', '.join(f'I({c.name})' for c in branch_parts)} are unknowns too (that is the 'modified' in modified nodal analysis)."
        )
    lines.append(f"That makes {layout.size} unknowns, so we need {layout.size} equations: KCL at every node, "
                 "plus one equation for each part that fixes a voltage.")
    steps.append(Step("Choose the unknowns", "Modified nodal analysis", lines))

    # 2. What each part's law says.
    by_part = {}
    for note in recorder.notes:
        by_part.setdefault(note.parts[0] if note.parts else "", []).append(note)
    for comp in circuit.components:
        notes = by_part.get(comp.name, [])
        if notes:
            steps.append(Step(f"What {comp.name} contributes", notes[0].law, [n.text for n in notes], (comp.name,)))

    # 3. KCL at every node, written out and then checked with the answer.
    for node in nodes:
        touching = [c for c in circuit.components if node in c.nodes]
        terms = [_kcl_term(c, node, solution) for c in touching]
        total = sum(t[2] for t in terms)
        steps.append(Step(
            f"KCL at node {node}",
            "Kirchhoff's current law",
            [f"The currents leaving node {node} through {', '.join(c.name for c in touching)} add up to zero:",
             "    " + _join(t[0] for t in terms) + " = 0",
             f"With the final answer: {_join(format_eng(t[2], 'A') for t in terms)} = {format_eng(total, 'A')} ✓"],
            tuple(c.name for c in touching),
            [_join(t[1] for t in terms) + " = 0"],
        ))

    # 4. The equation of each voltage source.
    for comp in branch_parts:
        if comp.letter == "V":
            n1, n2 = comp.nodes
            steps.append(Step(
                f"KVL for {comp.name}", "Kirchhoff's voltage law",
                [f"{comp.name} holds its + end {format_eng(comp.value, 'V')} above its - end:",
                 f"    {_v(n1)} − {_v(n2)} = {format_eng(comp.value, 'V')}"],
                (comp.name,), [f"{_vtex(n1)} - {_vtex(n2)} = {comp.value:g}"],
            ))

    # 5. The matrix, when it's small enough to read.
    if layout.size <= 8:
        names = recorder.unknowns
        width = max(len(n) for n in names)
        rows = []
        for i in range(layout.size):
            row = "  ".join(f"{_short(v):>9}" for v in recorder.matrix[i])
            rows.append(f"    [{row} ]  [{names[i]:>{width}}]  =  [{_short(recorder.rhs[i]):>9}]")
        steps.append(Step("Write the equations as a matrix", "Linear algebra",
                          ["Each row is one equation and each column belongs to one unknown, so the equations become A·x = b:"] + rows))

    # 6. Solve.
    nonlinear = [c.name for c in circuit.components if c.nonlinear]
    if nonlinear:
        lines = [f"{', '.join(nonlinear)} {'is' if len(nonlinear) == 1 else 'are'} nonlinear, so the equations were solved with Newton's "
                 "method: guess, replace each nonlinear part with its tangent line at the guess, solve, and repeat until "
                 f"the answer stops changing. That took {solution.iterations} iterations."]
    else:
        lines = ["Every part is linear, so a single solve of the matrix equation gives the exact answer."]
    lines += [f"    {_v(n)} = {format_eng(solution.v(n), 'V')}" for n in nodes]
    lines += [f"    I({c.name}) = {format_eng(float(solution.x[c.br]), 'A')}" for c in branch_parts]
    steps.append(Step("Solve", "Newton's method" if nonlinear else "Gaussian elimination", lines))

    # 7. Currents and powers.
    lines = []
    for comp in circuit.components:
        if comp.letter == "R":
            a, b = comp.nodes
            va, vb = solution.v(a), solution.v(b)
            i = (va - vb) / comp.value
            lines.append(f"{comp.name}: I = ({_v(a)} − {_v(b)}) / R = ({format_eng(va, 'V')} − {format_eng(vb, 'V')}) / "
                         f"{format_eng(comp.value, 'Ω')} = {format_eng(i, 'A')},  P = I²R = {format_eng(i * i * comp.value, 'W')}")
        elif comp.nodes:
            region = solution.region(comp.name)
            extra = f" ({region})" if region else ""
            lines.append(f"{comp.name}{extra}: I = {format_eng(solution.i(comp.name), 'A')},  P = V·I = {format_eng(solution.p(comp.name), 'W')}")
    steps.append(Step("Currents and power in every part", "Ohm's law and Joule's law", lines))

    # 8. Energy check.
    report = power_report(solution)
    lines = ["Absorbed power counts as positive and delivered power as negative (passive sign convention).",
             f"The sources deliver {format_eng(report.delivered, 'W')} and the other parts absorb {format_eng(report.absorbed, 'W')}.",
             f"Sum of all powers = {format_eng(report.imbalance, 'W')}, so energy is conserved " + ("✓" if report.balanced else "✗")]
    lines += ["WARNING: " + w for w in report.warnings]
    steps.append(Step("Check the power balance", "Tellegen's theorem (conservation of energy)", lines))

    return Walkthrough(f"How MiniSpice solved: {circuit.title or 'the circuit'}", steps), solution


def _short(value):
    """Compact number for the matrix display."""
    value = float(np.real(value))
    return "0" if value == 0 else f"{value:.4g}"
