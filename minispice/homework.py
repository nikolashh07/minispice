"""Homework checker and practice mode.

Write the circuit and your answers in one file, in the order you worked them out:

    * Homework 3, problem 2
    V1 1 0 12
    R1 1 2 6k
    R2 2 0 3k
    * answer: i(R1) = 1.33m
    * answer: v(2) = 4

`python -m minispice check problem.cir` says which answers are right. The first wrong one is the
step where your work split from the correct solution, and MiniSpice tries to name the mistake:
a flipped sign, a units slip, or a part that was forgotten or treated as a short.
"""

import random
import re
from dataclasses import dataclass, field

from .analysis.dc import operating_point
from .components.sources import VoltageSource
from .errors import MiniSpiceError
from .units import format_eng, parse_value

ANSWER = re.compile(r"^\*\s*answer:\s*(.+?)\s*=\s*(\S+)\s*$", re.I)
TOLERANCE = 0.02  # 2 %: what a careful hand calculation with rounded numbers should reach


@dataclass
class Answer:
    expr: str
    given: float
    correct: float
    ok: bool
    hint: str = ""


@dataclass
class HomeworkReport:
    answers: list = field(default_factory=list)

    @property
    def all_correct(self):
        return all(a.ok for a in self.answers)

    @property
    def first_wrong(self):
        return next((a for a in self.answers if not a.ok), None)

    def to_text(self):
        lines = []
        for n, a in enumerate(self.answers, 1):
            unit = _unit(a.expr)
            mark = "right" if a.ok else "WRONG"
            lines.append(f"{n}. {a.expr} = {format_eng(a.given, unit)}: {mark}")
        wrong = self.first_wrong
        if wrong is None:
            lines.append(f"\nAll {len(self.answers)} answers are right.")
        else:
            lines.append(f"\nYour work first goes wrong at {wrong.expr}: you have {format_eng(wrong.given, _unit(wrong.expr))}, "
                         f"but it should be {format_eng(wrong.correct, _unit(wrong.expr))}.")
            if wrong.hint:
                lines.append(wrong.hint)
            later = [a for a in self.answers[self.answers.index(wrong) + 1:] if not a.ok]
            if later:
                lines.append(f"({len(later)} later answer(s) are also off; they may just follow from this one.)")
        return "\n".join(lines)


def _unit(expr):
    return {"v": "V", "i": "A", "p": "W"}.get(expr.strip().lower()[:1], "")


def close(a, b, tol=TOLERANCE):
    return abs(a - b) <= tol * max(abs(b), 1e-12) + 1e-12


def read_answers(text):
    """[(expr, value)] from '* answer: v(2) = 5' lines, in order."""
    answers = []
    for line in text.splitlines():
        match = ANSWER.match(line.strip())
        if match:
            try:
                answers.append((match.group(1), parse_value(match.group(2))))
            except ValueError:
                raise MiniSpiceError(f"can't read the answer '{match.group(2)}' for {match.group(1)}") from None
    return answers


def check_answers(circuit, answers, tol=TOLERANCE):
    if not answers:
        raise MiniSpiceError("No answers found. Add lines like '* answer: v(2) = 5' to the circuit file.")
    solution = operating_point(circuit)
    report = HomeworkReport()
    for expr, given in answers:
        correct = solution.measure(expr)
        ok = close(given, correct, tol)
        report.answers.append(Answer(expr, given, correct, ok, "" if ok else diagnose(circuit, expr, given, correct, tol)))
    return report


def diagnose(circuit, expr, given, correct, tol=TOLERANCE):
    """Guess the mistake behind a wrong answer by testing what common slips would have produced."""
    if correct != 0 and close(given, -correct, tol):
        return ("The size is right but the sign is flipped. Check your current directions: MiniSpice uses the passive sign "
                "convention, where current flowing into a part's first (+) terminal is positive.")
    for factor, words in ((1e3, "1000 too big"), (1e-3, "1000 too small"), (1e6, "a million too big"), (1e-6, "a million too small")):
        if correct != 0 and close(given, correct * factor, tol):
            return f"The digits are right but the answer is {words}: check your units (k = 1000, m = 0.001, µ = 0.000001)."
    for comp in circuit.components:
        if comp.letter != "R":
            continue
        for change, words in (("open", f"left {comp.name} out (as if it were an open circuit)"),
                              ("short", f"treated {comp.name} as a short circuit (a plain wire)")):
            alternative = _what_if(circuit, comp.name, change, expr)
            if alternative is not None and close(given, alternative, tol) and not close(alternative, correct, tol):
                return f"Your answer is what you'd get if you {words}. Check how {comp.name} is connected."
    return ("It isn't a sign or units slip. Re-check the KCL equation at each node, or run with --explain "
            "to see the full solution step by step.")


def _what_if(circuit, name, change, expr):
    work = circuit.copy()
    comp = work.remove(name)
    if change == "short":
        work.add(VoltageSource(f"V_short_{name}", comp.nodes[0], comp.nodes[1], 0.0))
    try:
        return operating_point(work).measure(expr)
    except MiniSpiceError:
        return None  # removing it disconnected something, so that can't be the student's circuit


# ---- practice mode ---------------------------------------------------------------------------------

# Values chosen so series and parallel combinations come out as round numbers by hand.
NICE_R = [1e3, 2e3, 3e3, 4e3, 6e3, 12e3]
NICE_V = [3, 5, 6, 9, 10, 12, 15, 24]


@dataclass
class Problem:
    netlist: str
    questions: list
    level: int
    seed: int


def generate_problem(seed=None, level=1):
    """A random DC circuit to solve by hand, with the quantities to find."""
    if seed is None:
        seed = random.randrange(1_000_000)
    rng = random.Random(seed)
    v = rng.choice(NICE_V)
    r = [rng.choice(NICE_R) for _ in range(4)]
    lines = [f"* Practice problem (level {level}, seed {seed})", f"V1 1 0 {v}"]
    if level <= 1:
        lines += [f"R1 1 2 {r[0] / 1e3:g}k", f"R2 2 0 {r[1] / 1e3:g}k"]
        questions = ["i(R1)", "v(2)"]
    elif level == 2:
        lines += [f"R1 1 2 {r[0] / 1e3:g}k", f"R2 2 0 {r[1] / 1e3:g}k", f"R3 2 0 {r[2] / 1e3:g}k"]
        questions = ["i(R1)", "v(2)", "i(R3)"]
    elif level == 3:
        v2 = rng.choice(NICE_V)
        lines += [f"R1 1 2 {r[0] / 1e3:g}k", f"R2 2 0 {r[1] / 1e3:g}k", f"R3 2 3 {r[2] / 1e3:g}k", f"V2 3 0 {v2}"]
        questions = ["v(2)", "i(R1)", "i(R3)"]
    else:
        current = rng.choice([1, 2, 3, 5]) * 1e-3
        lines = [f"* Practice problem (level {level}, seed {seed})", f"I1 0 1 {current * 1e3:g}m",
                 f"R1 1 0 {r[0] / 1e3:g}k", f"R2 1 2 {r[1] / 1e3:g}k", f"R3 2 0 {r[2] / 1e3:g}k", f"R4 2 0 {r[3] / 1e3:g}k"]
        questions = ["v(1)", "i(R2)", "v(2)"]
    return Problem("\n".join(lines) + "\n", questions, level, seed)
