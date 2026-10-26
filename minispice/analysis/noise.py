"""Noise analysis: thermal (Johnson-Nyquist) noise from resistors and shot noise from junctions.

Each noise source is a tiny random current between two nodes, described by its power spectral
density S (A²/Hz): 4kT/R for a resistor, 2qI for a diode. Its contribution to the output is
|H(f)|² S, where H is the transfer from that current to the output voltage. Independent sources
add as powers, so the output noise density is sqrt(Σ |H|² S) in V/√Hz.

Finding H for every source would take one solve per source per frequency. The adjoint trick gets
them all at once: solve the transposed matrix with a unit "current" at the output, and the answer
at node a is the transfer from a current injected at node a.
"""

from dataclasses import dataclass, field

import numpy as np

from ..context import Context
from ..errors import CircuitError
from ..mna import Layout, assemble
from ..results import parse_probe
from ..units import parse_value
from .ac import frequencies
from .dc import operating_point


@dataclass
class NoiseResult:
    freqs: np.ndarray
    output_density: np.ndarray  # V/√Hz at the output
    contributions: dict = field(default_factory=dict)  # part name -> its V²/Hz at the output
    gain: np.ndarray = None  # |output / input source| when an input source is given
    output: str = ""
    input_source: str = None

    @property
    def input_density(self):
        """Noise referred to the input: the noise a perfect circuit would need at its input to match."""
        if self.gain is None:
            raise CircuitError("Give an input source to get input-referred noise.")
        return self.output_density / np.maximum(self.gain, 1e-300)

    def total_rms(self):
        """Total output noise voltage over the swept band: sqrt of the area under the PSD."""
        return float(np.sqrt(np.trapezoid(self.output_density ** 2, self.freqs)))

    def ranked_contributors(self):
        """Parts ordered by their share of the total noise power over the band."""
        totals = {name: float(np.trapezoid(psd, self.freqs)) for name, psd in self.contributions.items()}
        overall = sum(totals.values()) or 1.0
        return sorted(((name, power / overall) for name, power in totals.items()), key=lambda item: -item[1])


def noise_analysis(circuit, output, input_source=None, f_start=1.0, f_stop=1e6, points=10, sweep="dec"):
    kind, out_node, ref_node = parse_probe(output)
    if kind != "v":
        raise CircuitError("Noise output must be a voltage, like v(out) or v(out,ref)")
    x_op = operating_point(circuit).x if not circuit.is_linear else None
    layout = Layout(circuit)
    n = layout.size
    selector = np.zeros(n)
    for node, sign in ((out_node, 1.0), (ref_node, -1.0)):
        if node != "0":
            if node not in layout.node_index:
                raise CircuitError(f"There is no node '{node}'")
            selector[layout.node_index[node]] += sign
    source = circuit.get(input_source) if input_source else None
    if source is not None and not source.is_source:
        raise CircuitError(f"{source.name} isn't an independent source")

    freqs = frequencies(sweep, points, f_start, f_stop)
    out_psd = np.zeros(len(freqs))
    contributions = {}
    gains = np.zeros(len(freqs)) if source is not None else None
    op_ctx = Context(mode="dc", temperature=circuit.temperature)  # shot noise reads the operating-point currents
    for k, f in enumerate(freqs):
        # Every independent source is off: voltage sources are shorts, current sources opens.
        ctx = Context(mode="ac", omega=2 * np.pi * f, x_op=x_op, temperature=circuit.temperature, sources_on=set())
        system = assemble(circuit.components, layout, ctx, dtype=complex)
        matrix = system.dense() if n <= 2000 else system.sparse().toarray()
        try:
            z = np.linalg.solve(matrix.T, selector.astype(complex))
        except np.linalg.LinAlgError:
            raise CircuitError("The circuit matrix is singular at this frequency, so noise can't be computed.") from None
        for comp in circuit.components:
            for a, b, psd in comp.noise_sources(x_op if x_op is not None else np.zeros(n), op_ctx):
                density = psd(f) if callable(psd) else psd
                transfer = (z[a] if a >= 0 else 0) - (z[b] if b >= 0 else 0)
                power = abs(transfer) ** 2 * density
                out_psd[k] += power
                contributions.setdefault(comp.name, np.zeros(len(freqs)))[k] += power
        if source is not None:
            # Gain from the input source to the output, with only that source on at 1 V (or 1 A).
            saved = source.ac
            source.ac = 1.0
            ctx_in = Context(mode="ac", omega=2 * np.pi * f, x_op=x_op, temperature=circuit.temperature, sources_on={source.key})
            x = assemble(circuit.components, layout, ctx_in, dtype=complex).solve(layout)
            source.ac = saved
            gains[k] = abs(selector @ x)
    return NoiseResult(freqs, np.sqrt(out_psd), contributions, gains, output, input_source)


def noise_from_directive(circuit, directive):
    """.noise v(out) [input source] dec|oct|lin <points> <fstart> <fstop>"""
    import re

    match = re.match(r"\.noise\s+(v\([^)]*\))\s*(.*)$", directive.raw.strip(), re.I)
    if not match:
        raise CircuitError("Usage: .noise v(out) [input source] dec <points> <fstart> <fstop>")
    output, rest = match.group(1), match.group(2).split()
    source = None
    if rest and rest[0].lower() not in ("dec", "oct", "lin"):
        source = rest.pop(0)
    if len(rest) != 4:
        raise CircuitError("Usage: .noise v(out) [input source] dec <points> <fstart> <fstop>")
    return noise_analysis(circuit, output, source, parse_value(rest[2]), parse_value(rest[3]), parse_value(rest[1]), rest[0])
