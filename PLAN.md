# MiniSpice — Full Build Plan

MiniSpice is a circuit simulator written in Python. It reads or lets you draw a circuit, solves it using the laws of circuit theory, explains step by step which law it used and why, and checks itself against real hardware.

This plan is big on purpose. It's split into parts, and each part ends at a **milestone**, a point where MiniSpice is finished enough to put on GitHub and your resume. Even if you stop at Milestone 1, you have a real project.

---

## How to use this plan

The phases are built in order, all the way through, and reviewed together once the whole project is finished.

While building:
- Each phase's tests must pass before moving on to the next one.
- Every phase's hand-check circuit becomes an automated test, so the hand checks can be re-done on paper and compared at review time. They're also good interview stories.
- Commit after each part with a clear message, like "Part B: time and frequency," and tag the milestone versions (v0.1, v0.2, ...). At review time, push to GitHub and update the README.

---

## Project layout (final target)

```
minispice/
├── CLAUDE.md
├── PLAN.md
├── README.md
├── pyproject.toml
├── minispice/                # the Python engine
│   ├── __main__.py           # command line: python -m minispice
│   ├── netlist.py            # reads circuit files
│   ├── subcircuits.py        # reusable circuit blocks
│   ├── components/           # one file per component type
│   ├── mna.py                # builds and solves the circuit matrix
│   ├── analysis/
│   │   ├── dc.py
│   │   ├── sweep.py
│   │   ├── transient.py
│   │   ├── ac.py
│   │   ├── fourier.py
│   │   ├── noise.py
│   │   ├── montecarlo.py
│   │   └── sensitivity.py
│   ├── theorems.py           # Thevenin, Norton, superposition, max power
│   ├── power.py              # Joule heating, power balance
│   ├── explain.py            # explain mode
│   ├── homework.py           # answer checker
│   ├── schematic.py          # auto-drawn schematics
│   ├── plotting.py
│   └── hardware.py           # talks to a microcontroller
├── web/                      # browser app
│   ├── index.html
│   ├── editor/               # drag-and-drop schematic editor
│   ├── scope/                # oscilloscope and plot views
│   └── engine-bridge.js      # runs the Python engine in the browser
├── firmware/                 # code for the microcontroller
├── examples/                 # sample circuits with known answers
├── docs/                     # documentation site
└── tests/
```

---

## Design decisions (whole project)

- **Components:** each type is its own class that owns its `stamp()`, meaning it knows how to add itself to the matrix. Adding a new part means adding one new file in `components/`, and the solver never changes.
- **Explain recording starts in Phase 2:** every stamp and solve step can log a short note ("KCL at node 2: R1 adds 1 mS") to an optional recorder. Phase 26 turns those notes into the walkthrough instead of retrofitting every solver.
- **Passive sign convention everywhere:** positive current flows into a part's + terminal, and V × I is the power it absorbs. A source that's delivering power shows negative current and power, just like in textbooks and ngspice.
- **Python 3.12+ compatible:** avoid features that only exist in newer Python, so the engine runs in Pyodide (Phase 28).
- **Output in engineering notation:** results print like `5 V`, `-5 mA` and `1.5 kΩ`, while code and tests work with raw floats.

---

# PART A — Core DC engine

## Phase 0: Setup

**Goal:** an organized, empty project.

**Tasks**
- Git repo, Python `.gitignore`, virtual environment.
- Install numpy, matplotlib, pytest.
- Create the `minispice/` and `tests/` folders, plus a short README.

**Done when:** `pytest` runs cleanly and the first commit is made.

---

## Phase 1: Netlist parser

**Goal:** turn a text file into Python objects.

**Format** (node 0 is ground):
```
* comment
V1 1 0 DC 10
R1 1 2 1k
R2 2 0 1k
```
Support unit suffixes p, n, u, m, k, meg, g.

**Design decisions**
- **Node names:** numbers or names (`1`, `in`, `out`, `vcc`). Ground is `0`, and `gnd` also works. The solver maps names to matrix rows internally.
- **Names are case-insensitive:** `R1` and `r1` are the same part (so a duplicate is an error), and `OUT` and `out` are the same node. This matches SPICE.
- **Unit suffixes follow the SPICE rule, case-insensitive:** `m`/`M` = milli, `meg`/`MEG` = mega, `k`/`K` = kilo, `g`/`G` = giga. So `1M` is 1 milli-ohm, not 1 megohm. This keeps netlists from the internet (Phase 18) and ngspice comparisons (Phase 23) correct.
- **Forgiving values:** trailing unit letters are ignored (`1kohm`, `10V`, `1uF`), and `DC` is optional on sources (`V1 1 0 10`).
- **Errors:** check every line, then raise one error that lists every problem with its line number.

**Tasks**
- Parse components (name, nodes, value).
- Handle comments, blank lines, and suffixes.
- Clear errors with line numbers.

**Hand check:** R1 parses as 1000 ohms between nodes 1 and 2.

---

## Phase 2: DC nodal analysis

**Laws:** Ohm's law, Kirchhoff's current law (KCL).

**Big idea:** at every node, current in equals current out. That gives one equation per node, which we put in a matrix and solve.

**Tasks**
- Stamp resistors into the conductance matrix.
- Add current sources to the right-hand side.
- Solve for node voltages.

**Hand check:** 1 mA into a 2k resistor to ground gives 2 V.

---

## Phase 3: Modified nodal analysis (voltage sources)

**Laws:** Kirchhoff's voltage law (KVL).

**Big idea:** a voltage source fixes the voltage between two nodes, but its current is unknown, so it gets an extra row and column in the matrix.

**Tasks**
- Voltage source stamps and branch currents.
- Detect unsolvable circuits (floating nodes, loops of voltage sources) and explain why.

**Hand checks**
- 10 V divider with two 1k resistors: 5 V in the middle, 5 mA.
- A two-source problem from your textbook.

---

## Phase 4: Power and energy

**Laws:** Joule's law, conservation of energy (Tellegen's theorem).

**Tasks**
- Power for every component, with a clear sign convention.
- Check that total power sums to zero.
- Optional power ratings with overheating warnings.

**Hand check:** divider resistors each absorb 25 mW, and the source delivers 50 mW.

---

## Phase 5: Circuit theorems

**Laws:** Thevenin, Norton, superposition, maximum power transfer.

**Tasks**
- Thevenin and Norton equivalents between any two nodes.
- Superposition breakdown, one source at a time, confirming the parts add up.
- Best load resistance and its maximum power.

**Hand check:** a textbook Thevenin problem matches the book.

---

## Phase 6: Command line and examples

**Goal:** make MiniSpice usable by anyone.

**Tasks**
- `python -m minispice examples/divider.cir --dc`
- Clean, readable output tables.
- An `examples/` folder where every circuit has its expected answer, and a test that checks them all.

### Milestone 1 (v0.1): DC simulator
Push to GitHub, write the README, tag v0.1. This is already resume-worthy.

---

# PART B — Time and frequency

## Phase 7: Transient analysis

**Laws:** capacitor law (current = C times rate of change of voltage), Faraday's and Lenz's laws for inductors.

**Big idea:** step through time. At each step, a capacitor or inductor acts like a resistor plus a source (a "companion model"), so the DC solver still works.

**Tasks**
- Backward Euler companion models.
- Time-stepping loop, plus step and pulse sources.
- Plots of voltage vs time.

**Hand check:** RC charging reaches about 63.2% of the source voltage after one time constant (R times C). The whole curve matches the exact formula.

---

## Phase 8: Better time stepping

**Goal:** accurate and fast transient simulation.

**Tasks**
- Trapezoidal integration (more accurate than backward Euler).
- Adaptive time step: small steps when things change fast, big steps when they don't.
- Sine and piecewise-linear sources.

**Hand check:** an underdamped RLC circuit rings at about 1 divided by (2 pi times the square root of L times C). Compare the decay to the textbook formula.

---

## Phase 9: AC analysis and Bode plots

**Laws:** complex impedance, phasors.

**Tasks**
- Complex impedance for R, L, and C.
- Frequency sweep, with Bode magnitude (dB) and phase plots.

**Hand check:** an RC low-pass filter is down 3 dB with a phase of -45 degrees at 1 divided by (2 pi R C).

---

## Phase 10: Fourier analysis

**Laws:** Fourier series and transform.

**Tasks**
- FFT of any transient result, with spectrum plots.
- Total harmonic distortion (THD) measurement.

**Hand check:** a square wave shows odd harmonics with sizes in the ratio 1, 1/3, 1/5.

---

## Phase 11: Transformers and switches

**Laws:** mutual inductance, Faraday's law.

**Tasks**
- Coupled inductors with a coupling factor k.
- An ideal transformer model.
- Time-controlled switches (open and close at set times).

**Hand check:** a 10:1 transformer steps 120 V down to 12 V, and currents scale the opposite way.

### Milestone 2 (v0.2): time and frequency
Tag v0.2. Add RC, RLC, and filter plots to the README.

---

# PART C — Active and nonlinear components

## Phase 12: Controlled sources

**Goal:** the building blocks for transistors and op-amps.

**Tasks**
- All four types: voltage-controlled voltage source, voltage-controlled current source, current-controlled voltage source, and current-controlled current source.

**Hand check:** a voltage-controlled current source with gain 0.01 driving a 1k load, with 1 V of control, gives 10 V across the load.

---

## Phase 13: Op-amps

**Tasks**
- Ideal op-amp model.
- Realistic model with finite gain, output limits (saturation), and bandwidth.

**Hand checks**
- Inverting amp: gain = minus Rf divided by Rin.
- Non-inverting amp: gain = 1 plus Rf divided by Rg.
- The output clips at the supply rails.

---

## Phase 14: Diodes and Newton's method

**Laws:** Shockley diode equation.

**Big idea:** guess, replace the diode with a straight-line approximation at the guess, solve, repeat until the answer stops changing.

**Tasks**
- Diode model, a Newton-Raphson loop, and a convergence check.
- Voltage limiting so the solver doesn't blow up.
- Zener diodes and LEDs (as diodes with a different turn-on voltage).

**Hand check:** 5 V source, 1k resistor, one diode gives about 0.6–0.7 V across the diode and about 4.3 mA.

---

## Phase 15: Transistors (BJT and MOSFET)

**Laws:** Ebers-Moll (BJT), square-law model (MOSFET).

**Tasks**
- NPN and PNP BJTs.
- N-channel and P-channel MOSFETs with cutoff, linear, and saturation regions.
- Report which region each transistor is in.

**Hand checks**
- BJT: a common-emitter bias circuit from your textbook.
- MOSFET in saturation: drain current = one half times k times (Vgs minus Vt) squared.
- A CMOS inverter flips its output when the input crosses the middle.

---

## Phase 16: Temperature

**Laws:** thermal voltage (kT/q), resistor temperature coefficients.

**Tasks**
- A global circuit temperature.
- Resistors and diodes change behavior with temperature.

**Hand check:** a silicon diode's voltage drops roughly 2 mV per degree C of heating.

### Milestone 3 (v0.3): semiconductors
Tag v0.3. MiniSpice can now simulate real amplifier and logic circuits.

---

# PART D — Advanced analyses

## Phase 17: Sweeps

**Tasks**
- DC sweep: vary a source and plot the result (this gives diode and transistor curves).
- Parameter sweep: rerun any analysis for a list of component values.

**Hand check:** sweeping a diode's voltage reproduces the exponential curve from Phase 14.

---

## Phase 18: Subcircuits and SPICE compatibility

**Tasks**
- `.subckt` blocks you can reuse, like an op-amp made of transistors.
- `.include` and `.model` lines.
- Read standard SPICE netlists, so MiniSpice can open circuits from the internet.

**Hand check:** a subcircuit version of the divider gives the same answer as the flat one.

---

## Phase 19: Speed

**Tasks**
- Sparse matrices (scipy), since big circuits are mostly zeros.
- Benchmark: time MiniSpice on circuits with 10, 100, 1,000, and 10,000 nodes.
- Profile and fix the slowest part.

**Hand check:** results with sparse matrices match the dense results exactly.

---

## Phase 20: Tolerances and Monte Carlo

**Goal:** real resistors aren't perfect, so show what that does to the circuit.

**Tasks**
- Tolerances on components (like a 5% resistor).
- Run the circuit hundreds of times with random values and show a histogram of results.
- Worst-case analysis.

**Hand check:** a divider with two 5% resistors gives a middle voltage that stays within the range you calculate by hand.

---

## Phase 21: Sensitivity analysis

**Tasks**
- Which components affect the output the most?
- A ranked list, so a designer knows which parts need tight tolerances.

**Hand check:** in a divider, both resistors have equal and opposite sensitivity.

---

## Phase 22: Noise analysis

**Laws:** Johnson-Nyquist thermal noise, shot noise.

**Tasks**
- Noise from every resistor and diode.
- Total output noise vs frequency.

**Hand check:** a 1k resistor at room temperature has about 4 nV per root hertz of noise.

---

## Phase 23: Validation against ngspice

**Goal:** prove MiniSpice against an industry-standard simulator.

**Tasks**
- Run the same circuits in ngspice (free and open source).
- Automated comparison tests, with a results table in the README.

### Milestone 4 (v0.4): pro-level analysis
Tag v0.4. The ngspice comparison is a strong credibility point.

---

# PART E — Visuals (2D)

## Phase 24: Auto-drawn schematics

**Tasks**
- Draw circuits from a netlist using the `schemdraw` library.
- A simple layout algorithm. Neat placement for any circuit is a hard problem, so start with series and parallel circuits and accept rough layouts for complex ones.
- Export as PNG and SVG.

---

## Phase 25: Results on the schematic

**Tasks**
- Label nodes with voltages and parts with currents and power.
- Color wires by voltage (like a heat map).
- Flag overheating parts in red.

---

## Phase 26: Explain mode

**Goal:** the standout feature.

**Tasks**
- Every solver step records which law it used and why ("Applied KCL at node 2...").
- `--explain` prints a plain-English walkthrough.
- Export the walkthrough as a formatted PDF or LaTeX file.

**Done when:** explain mode on a homework problem reads like a good tutor solving it.

---

## Phase 27: Homework checker

**Tasks**
- Enter a circuit and your answer, and MiniSpice says right or wrong.
- If you're wrong, it shows the first step where your answer and the correct one split apart.
- A "practice mode" that generates random circuits to solve.

### Milestone 5 (v0.5): visual and educational
Tag v0.5. Add screenshots and a GIF of explain mode to the README.

---

# PART F — Web app and editor

## Phase 28: Run MiniSpice in the browser

**Big idea:** Pyodide runs Python (including numpy and scipy) directly in a web browser. No server is needed, and you can host it free on GitHub Pages.

**Tasks**
- Load the MiniSpice engine with Pyodide.
- A simple page: paste a netlist, click Solve, see results.
- Host it on GitHub Pages.

---

## Phase 29: Drag-and-drop schematic editor

**Tasks**
- A parts palette: resistor, sources, capacitor, inductor, diode, transistors, op-amp, ground.
- Place, rotate, and delete parts on a snapping grid.
- Draw wires. The editor works out which wires form the same node.
- Converts the drawing to a netlist and back.
- Undo and redo, and save and load to a file.

---

## Phase 30: Live simulation

**Tasks**
- Sliders on component values that update results instantly.
- Animated dots showing current flowing through wires, with speed matching the current.
- Hover over anything to see its voltage, current, and power.

---

## Phase 31: Virtual instruments

**Tasks**
- A virtual oscilloscope: drop probes on nodes and watch waveforms over time.
- A virtual multimeter.
- A Bode plot viewer and a spectrum analyzer view.

---

## Phase 32: Explain mode in the browser

**Tasks**
- Click "Explain" and step through the solution with the relevant parts highlighted at each step.

### Milestone 6 (v1.0): full web app
Tag v1.0. You now have a live link to put on your resume, which recruiters can click and try themselves.

---

# PART G — Hardware integration (ties to the electronics project)

## Phase 33: Simulation vs reality

**Tasks**
- Build the divider, RC, diode, and op-amp circuits from `examples/` on a breadboard.
- Measure them with a multimeter (and an oscilloscope if you have lab access).
- Add a README table comparing simulated and measured values, and explain the differences (tolerance, meter resistance, and so on).

---

## Phase 34: Live hardware link

**Tasks**
- Arduino or ESP32 firmware that reads voltages with its ADC pins and sends them over USB.
- MiniSpice reads the data with `pyserial` and overlays measured values on simulated ones, live.
- In the web app, show real and simulated waveforms on the same virtual oscilloscope.

---

## Phase 35: 3D breadboard view (stretch)

**Tasks**
- A 3D view of a MiniSpice circuit laid out on a virtual breadboard, using Three.js in the browser.
- It helps you build the physical circuit correctly.

---

# PART H — Ship it

## Phase 36: Packaging

**Tasks**
- `pyproject.toml` and publishing to PyPI so anyone can `pip install` it. Check first whether the name "minispice" is already taken on PyPI. If it is, use something like `minispice-sim`.
- Version numbers and a changelog.

---

## Phase 37: Docs and testing

**Tasks**
- A documentation site with MkDocs, hosted on GitHub Pages.
- GitHub Actions that run all tests on every push, with a test coverage badge in the README.

---

## Phase 38: Portfolio polish

**Tasks**
- A README that a recruiter understands in 30 seconds: what it does, screenshots, live demo link, laws supported.
- A 2-minute demo video.
- A short write-up or blog post on how you built it and what was hardest.
- Pin it on GitHub and link it on LinkedIn and your resume.

---

## Laws and principles covered

Ohm's law · Kirchhoff's current and voltage laws · Joule's law · Tellegen's theorem · Thevenin's and Norton's theorems · superposition · maximum power transfer · capacitor law · Faraday's law · Lenz's law · mutual inductance · impedance and phasors · Fourier analysis · Shockley diode equation · Ebers-Moll model · MOSFET square-law model · thermal voltage · Johnson-Nyquist noise · Newton's method · numerical integration
