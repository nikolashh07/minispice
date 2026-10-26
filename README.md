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

## What it does (v0.1)

- Reads SPICE-style netlists: unit suffixes (`1k`, `4.7u`, `10meg`), comments, `.param`, `.include`, subcircuits.
- DC operating point by modified nodal analysis (Ohm's law, KCL, KVL).
- Power of every part with the passive sign convention, and a conservation-of-energy check.
- Thevenin and Norton equivalents, superposition, and maximum power transfer.
- Clear error messages for floating nodes, voltage-source loops and bad netlist lines.

Run the tests with `pytest`.
