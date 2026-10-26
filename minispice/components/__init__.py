"""Component types, one file per type. REGISTRY maps a netlist letter to its class.

Adding a new part means writing one new class with parse() and stamp() and listing it here.
"""

from .resistor import Resistor
from .sources import CurrentSource, VoltageSource

REGISTRY = {cls.letter: cls for cls in (Resistor, VoltageSource, CurrentSource)}
