"""Explain mode: records which law each solver step used, in plain English.

Every stamp can leave a short note on a Recorder ("Ohm's law: R1 adds 1 mS at nodes 1 and 2").
The walkthrough functions further down turn those notes into a step-by-step solution.
"""

from dataclasses import dataclass, field


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
