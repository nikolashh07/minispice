# Changelog

Versions follow [semantic versioning](https://semver.org): the first number changes when netlists or
the Python API change in a way that breaks existing use, the second when features are added, the
third for fixes.

## 1.1.0

- Real hardware: lab circuits with measurement sheets, `minispice compare` (explains differences with
  simulated part tolerances and meter loading), Arduino/ESP32 probe firmware, `minispice measure`
  and `minispice overlay`, and live board readings on the browser oscilloscope.
- 3D breadboard view with hole-by-hole build instructions and resistor color bands.
- Packaging: `pip install minispice` with a `minispice` command, and optional extras
  (`fast`, `schematic`, `hardware`, `all`).
- Documentation site and continuous integration with test coverage.

## 1.0.0: full web app

- The engine runs in the browser with Pyodide, in a Web Worker.
- Drag-and-drop schematic editor with live simulation, sliders and animated current flow.
- Oscilloscope, multimeter, Bode plotter and spectrum analyzer.
- Explain mode in the browser, highlighting the parts at each step.

## 0.5.0: visual and educational

- Auto-drawn schematics, annotated with voltages, currents and power, wires colored by voltage.
- Explain mode with text, Markdown, LaTeX and PDF export.
- Homework checker that finds the first wrong step and diagnoses common mistakes, and practice mode.

## 0.4.0: pro-level analysis

- DC and parameter sweeps, subcircuits with parameters, SPICE netlist compatibility.
- Sparse matrices and a benchmark up to 10,000 nodes.
- Monte Carlo, worst-case and sensitivity analysis.
- Thermal and shot noise analysis.
- ngspice comparison tool.

## 0.3.0: semiconductors

- Controlled sources, ideal and realistic op-amps.
- Diodes, Zeners and LEDs with Newton's method and junction voltage limiting.
- BJTs (Ebers-Moll) and MOSFETs (square law) with operating regions.
- Temperature effects.

## 0.2.0: time and frequency

- Transient analysis with backward Euler and trapezoidal integration and adaptive time steps.
- AC analysis and Bode plots, Fourier analysis and THD.
- Coupled inductors, ideal transformers and time-controlled switches.

## 0.1.0: DC simulator

- Netlist parser, modified nodal analysis, power balance, Thevenin/Norton/superposition/maximum
  power transfer, and the command line.
