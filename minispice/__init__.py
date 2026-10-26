"""MiniSpice: a circuit simulator that solves circuits with circuit laws and explains each step."""

__version__ = "1.1.0"

from .analysis.dc import operating_point
from .circuit import Circuit
from .errors import CircuitError, ConvergenceError, MiniSpiceError, NetlistError
from .netlist import load, parse
from .units import format_eng, parse_value

__all__ = [
    "Circuit",
    "CircuitError",
    "ConvergenceError",
    "MiniSpiceError",
    "NetlistError",
    "format_eng",
    "load",
    "operating_point",
    "parse",
    "parse_value",
]
