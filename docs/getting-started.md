# Getting started

## Install

```
pip install minispice            # the simulator and plots
pip install "minispice[all]"     # also schematics, sparse matrices for huge circuits, and hardware
```

Or from a copy of the repository:

```
python -m venv .venv
.venv\Scripts\activate           # Windows
source .venv/bin/activate        # Mac and Linux
pip install -r requirements.txt
```

`minispice` and `python -m minispice` are the same command.

## Your first circuit

Save this as `divider.cir`:

```
* Voltage divider
V1 1 0 DC 10
R1 1 2 1k
R2 2 0 1k
.op
```

Node `0` is ground. Each line after the comment is one part: its name, the nodes it connects,
and its value. Run it:

```
python -m minispice divider.cir
```

```
Node  Voltage
----  -------
1     10 V
2     5 V

Part  Type            Voltage  Current  Power absorbed
----  --------------  -------  -------  --------------
V1    voltage source  10 V     -5 mA    -50 mW
R1    resistor        5 V      5 mA     25 mW
R2    resistor        5 V      5 mA     25 mW
```

The source's current and power are negative because it *delivers* power. MiniSpice uses the
passive sign convention: current flowing into a part's first terminal is positive, and V × I is
the power the part absorbs.

## Next steps

- Ask for an explanation: `python -m minispice divider.cir --explain`
- Watch a capacitor charge: `python -m minispice examples/rc_charge.cir --probe "v(2)" --plot`
- Draw circuits instead of typing them: `python web/serve.py`, then open http://localhost:8000
- Use it from Python:

```python
import minispice

circuit = minispice.parse("V1 1 0 10\nR1 1 2 1k\nR2 2 0 1k")
solution = minispice.operating_point(circuit)
print(solution.v(2), solution.i("R1"), solution.p("V1"))   # 5.0 0.005 -0.05
```
