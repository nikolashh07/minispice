"""Component types, one file per type. REGISTRY maps a netlist letter to its class.

Adding a new part means writing one new class with parse() and stamp() and listing it here.
"""

from .bjt import BJT
from .capacitor import Capacitor
from .controlled import CCCS, CCVS, VCCS, VCVS
from .diode import Diode
from .inductor import Inductor
from .magnetics import IdealTransformer, MutualInductance
from .mosfet import MOSFET
from .opamp import OpAmp
from .resistor import Resistor
from .sources import CurrentSource, VoltageSource
from .switch import TimeSwitch

REGISTRY = {
    cls.letter: cls
    for cls in (
        Resistor, VoltageSource, CurrentSource, Capacitor, Inductor, MutualInductance, IdealTransformer, TimeSwitch,
        VCVS, VCCS, CCCS, CCVS, OpAmp, Diode, BJT, MOSFET,
    )
}
