# MiniSpice

MiniSpice is a circuit simulator written in Python. Give it a circuit, as a text netlist or a
drawing in the browser, and it works out every voltage, current and power using the laws of
circuit theory. Then it can explain, step by step, which law it used and why.

![Explain mode](images/explain.gif)

## What it can do

- **DC, transient, AC, Fourier and noise analysis**, plus sweeps, Monte Carlo, worst case and sensitivity.
- **Real components:** resistors, capacitors, inductors, transformers, switches, sources with
  pulse/sine/PWL waveforms, controlled sources, op-amps, diodes, LEDs, Zeners, BJTs and MOSFETs.
- **Circuit theorems:** Thevenin, Norton, superposition and maximum power transfer.
- **Explain mode:** a walkthrough of the solution (unknowns, KCL at every node, the matrix, the
  answer, the power balance), exported as text, Markdown, LaTeX or PDF.
- **A homework checker** that finds the first wrong step and names the likely mistake.
- **A browser app** with a drag-and-drop editor, live simulation, animated current, an
  oscilloscope, a Bode plotter, a spectrum analyzer and a 3D breadboard view. [Open the app](app/).
- **Real hardware:** compare multimeter readings with the simulation, or stream a
  microcontroller's measurements on top of it.

## Laws and principles used

Ohm's law · Kirchhoff's current and voltage laws · Joule's law · Tellegen's theorem · Thevenin's
and Norton's theorems · superposition · maximum power transfer · the capacitor law · Faraday's and
Lenz's laws · mutual inductance · impedance and phasors · Fourier analysis · the Shockley diode
equation · the Ebers-Moll model · the MOSFET square law · thermal voltage · Johnson-Nyquist and
shot noise · Newton's method · numerical integration
