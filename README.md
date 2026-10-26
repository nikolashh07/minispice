# MiniSpice

A Python circuit simulator that solves netlists with circuit laws and explains each step.

## Quick start

```
python -m venv .venv
.venv\Scripts\activate          (Windows)   or   source .venv/bin/activate
pip install -r requirements.txt
python -m minispice examples/divider.cir --dc
```

```
DC operating point
==================
Node  Voltage
----  -------
1     10 V
2     5 V

Part  Type            Voltage  Current  Power absorbed
----  --------------  -------  -------  --------------
V1    voltage source  10 V     -5 mA    -50 mW
R1    resistor        5 V      5 mA     25 mW
R2    resistor        5 V      5 mA     25 mW

Sources deliver 50 mW, parts absorb 50 mW: balanced (sum of all powers = 0 W)
```

## Semiconductors (v0.3)

```
python -m minispice examples/bjt_bias.cir
python -m minispice examples/inverting_amp.cir
python -m minispice examples/two_stage_amp.cir --probe "v(out)" --plot
```

- Controlled sources (E, G, F, H), and ideal or realistic op-amps (finite gain, rail clipping, gain-bandwidth).
- Diodes (Shockley equation), Zener diodes and LEDs, solved with Newton's method and SPICE-style voltage limiting.
- NPN/PNP BJTs (Ebers-Moll) and N/P-channel MOSFETs (square law), with the operating region of each reported.
- Circuit temperature: diode and BJT currents follow kT/q and IS(T); resistors have temperature coefficients.

## Time and frequency (v0.2)

| RC charging | Underdamped RLC | RC low-pass Bode plot |
|---|---|---|
| ![RC charging](docs/images/rc_charge.png) | ![RLC ringing](docs/images/rlc_ring.png) | ![Bode plot](docs/images/rc_lowpass_bode.png) |

```
python -m minispice examples/rc_charge.cir --probe "v(2)" --plot
python -m minispice examples/rc_lowpass.cir --probe "v(2)" --plot
python -m minispice examples/square_wave.cir
```

- Transient analysis with backward Euler or trapezoidal integration and adaptive time steps.
- Step, pulse, sine, piecewise-linear and exponential sources.
- AC analysis with Bode magnitude and phase plots.
- Fourier analysis: harmonics, THD and spectra.
- Coupled inductors, ideal transformers and time-controlled switches.

## DC analysis (v0.1)

- Reads SPICE-style netlists: unit suffixes (`1k`, `4.7u`, `10meg`), comments, `.param`, `.include`, subcircuits.
- DC operating point by modified nodal analysis (Ohm's law, KCL, KVL).
- Power of every part with the passive sign convention, and a conservation-of-energy check.
- Thevenin and Norton equivalents, superposition, and maximum power transfer.
- Clear error messages for floating nodes, voltage-source loops and bad netlist lines.

Run the tests with `pytest`.
