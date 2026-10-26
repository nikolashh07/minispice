# Web app

[Open the app](../app/) · run it locally with `python web/serve.py`

The browser app runs the same Python engine as the command line, using
[Pyodide](https://pyodide.org) (Python compiled to WebAssembly). The first visit downloads about
10 MB; after that it loads from the browser cache. Nothing is sent to a server.

## Drawing circuits

- Pick a part from the palette and click the grid to place it. Right-click or Esc when done.
- **Wire** mode: click to start, click to bend or finish. A wire that ends on a pin or another
  wire connects to it, including in the middle of a wire (a T junction).
- Drag parts to move them. R rotates, Delete removes, Ctrl+Z and Ctrl+Y undo and redo.
- Select a part to edit its name and value in the inspector. Values use netlist syntax (`4.7k`,
  `PULSE(0 5 0 1u 1u 1m 2m)`, `led_red`).
- **Save** downloads the drawing; **Open** reads a saved drawing or any netlist. **Export .cir**
  gives the netlist for the command line. Netlists exported from the editor keep the layout in
  comments, so they open as the same drawing.

## Live simulation

With **Live** on, every change re-solves the circuit:

- **Node voltages** are written next to the wires.
- **Hovering** over a part or wire shows its voltage, current and power.
- **Dots** flow along the wires and through the parts. Their speed grows with the logarithm of
  the current, so microamps and amps are both visible.
- **The slider** in the inspector sweeps a part's value from a tenth to ten times its value while
  you watch.
- **Overheating** parts (power above `rating=`) turn red.

## Instruments

| Instrument | Use |
|---|---|
| Oscilloscope | Pick the Probe tool, click up to four wires, set the run time and press Run. **Connect board** overlays a microcontroller's live readings (Chrome or Edge). |
| Multimeter | Volts between any two nodes, or the current or power of any part. Updates live. |
| Bode plotter | Drives a chosen voltage source with 1 V AC and plots gain and phase at a chosen node, with the −3 dB frequency. |
| Spectrum analyzer | FFT of a node's waveform over the oscilloscope's run time. |

## Explain

The Explain tab steps through the DC solution. The parts each step talks about turn orange on the drawing.

## 3D breadboard

**3D breadboard** opens a model of the current circuit on a breadboard, with hole-by-hole build
instructions and real resistor color bands. Click a step to highlight its part.

## How the page talks to Python

The engine runs in a Web Worker so long simulations never freeze the page. The page sends
`{function, arguments}` as a message; the worker calls `minispice.webapi.call(name, json)` in
Pyodide and posts the JSON answer back. Only JSON text crosses between JavaScript and Python.
