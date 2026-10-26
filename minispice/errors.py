"""Error types. Every message should tell the user what is wrong with their circuit and how to fix it."""


class MiniSpiceError(Exception):
    """Base class, so callers can catch everything MiniSpice raises on purpose."""


class NetlistError(MiniSpiceError):
    """One or more lines of a netlist could not be read.

    The parser checks every line before raising, so the user can fix all problems in one go
    instead of discovering them one run at a time.
    """

    def __init__(self, problems, source="netlist"):
        # problems: list of (line label or None, message)
        self.problems = list(problems)
        lines = [f"Found {len(self.problems)} problem(s) in the {source}:"]
        for where, message in self.problems:
            prefix = f"{where}: " if where else ""
            lines.append(f"  {prefix}{message}")
        super().__init__("\n".join(lines))


class CircuitError(MiniSpiceError):
    """The circuit was read fine but cannot be solved (floating node, loop of voltage sources, ...)."""


class ConvergenceError(CircuitError):
    """Newton's method could not find a solution for a nonlinear circuit."""
