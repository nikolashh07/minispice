"""Everything a component needs to know when it stamps itself: which analysis, what time, which guess."""

from dataclasses import dataclass, field

import numpy as np

K_BOLTZMANN = 1.380649e-23
Q_ELECTRON = 1.602176634e-19
T_NOMINAL_C = 27.0  # SPICE measures model parameters at 27 °C


def kelvin(celsius):
    return celsius + 273.15


def thermal_voltage(celsius):
    """kT/q, about 25.9 mV at room temperature. Sets how sharply diodes and transistors turn on."""
    return K_BOLTZMANN * kelvin(celsius) / Q_ELECTRON


@dataclass
class Context:
    mode: str = "dc"  # "dc", "tran" or "ac"
    time: float = 0.0
    h: float = 0.0  # transient time step
    method: str = "trap"  # "be" (backward Euler) or "trap" (trapezoidal)
    x: np.ndarray = None  # the guess the nonlinear parts linearize around
    x_prev: np.ndarray = None  # solution at the previous time point
    state: dict = field(default_factory=dict)  # per-part history for capacitors, inductors, ...
    omega: float = 0.0  # AC angular frequency, rad/s
    temperature: float = T_NOMINAL_C
    gmin: float = 1e-12  # tiny conductance across junctions so a turned-off device can't float a node
    gshunt: float = 0.0  # conductance from every node to ground, only during gmin stepping
    source_scale: float = 1.0  # < 1 during source stepping
    sources_on: set = None  # superposition: names of independent sources left on (None = all)
    recorder: object = None  # explain-mode note taker
    limits: dict = field(default_factory=dict)  # last junction voltages, for Newton voltage limiting
    limited: bool = False  # set when a part limited its voltage this iteration
    x_op: np.ndarray = None  # DC operating point that AC and noise linearize around

    def source_factor(self, comp):
        """How much of an independent source to apply: 0 when switched off, 1 normally."""
        if self.sources_on is not None and comp.key not in self.sources_on:
            return 0.0
        return self.source_scale

    def note(self, law, text, parts=()):
        if self.recorder is not None:
            self.recorder.note(law, text, parts)

    @property
    def explaining(self):
        return self.recorder is not None
