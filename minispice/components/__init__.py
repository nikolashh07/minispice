"""Component types, one file per type. REGISTRY maps a netlist letter to its class.

Adding a new part means writing one new class with parse() and stamp() and listing it here.
"""

from .capacitor import Capacitor
from .inductor import Inductor
from .magnetics import IdealTransformer, MutualInductance
from .resistor import Resistor
from .sources import CurrentSource, VoltageSource
from .switch import TimeSwitch

REGISTRY = {
    cls.letter: cls
    for cls in (Resistor, VoltageSource, CurrentSource, Capacitor, Inductor, MutualInductance, IdealTransformer, TimeSwitch)
}
