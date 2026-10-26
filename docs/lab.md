# Simulation vs reality

A simulator is only worth trusting if it matches real circuits. These five lab circuits are built
from cheap parts and powered from an Arduino's 5 V pin, so they can be built on any breadboard
and measured with a basic multimeter (and, for the RC circuit, the MiniSpice probe firmware).

| Lab | Circuit file | What it shows |
|---|---|---|
| 1 | `examples/lab/lab_divider.cir` | Ohm's law and KVL with 5 % resistors |
| 2 | `examples/lab/lab_highz_divider.cir` | The multimeter itself changes the circuit |
| 3 | `examples/lab/lab_diode.cir` | A real diode's forward voltage |
| 4 | `examples/lab/lab_opamp.cir` | A non-inverting amplifier on a single supply |
| 5 | `examples/lab/lab_rc.cir` | RC charging, measured with the microcontroller |

## How to run a lab

1. Build the circuit. Open the circuit in the web app's 3D breadboard view for hole-by-hole instructions.
2. Measure each quantity listed in the matching `.csv` sheet and type the readings into its
   `measured` column. Measure the supply too: USB 5 V is often 4.8 to 5.1 V. If it's off, change
   `VSUP` in the `.cir` file to the real value.
3. Compare: `python -m minispice compare examples/lab/lab_divider.cir examples/lab/lab_divider.csv`
4. Update this page's table: `python tools/lab_table.py`

For the RC lab, record with the probe firmware (see `firmware/README.md`) and overlay:

```
python -m minispice measure --port COM3 --seconds 0.2 --out rc.csv
python -m minispice overlay examples/lab/lab_rc.cir rc.csv --probe "v(cap)" --channel a1
```

## Results

The Measured column is empty until the labs have been built and measured.

<!-- lab-table:start -->
| Circuit | Quantity | Simulated | Tolerance range | With a 10 MΩ meter | Measured | Difference |
|---|---|---:|---:|---:|---:|---:|
| lab_diode | v(d) | 653.2 mV | 650.9 mV to 655.7 mV | 653.2 mV |  |  |
| lab_diode | v(vcc,d) | 4.347 V | 4.344 V to 4.349 V | 4.347 V |  |  |
| lab_divider | v(vcc) | 5 V | 5 V to 5 V | 5 V |  |  |
| lab_divider | v(mid) | 1.599 V | 1.492 V to 1.709 V | 1.598 V |  |  |
| lab_highz_divider | v(mid) | 2.5 V | 2.375 V to 2.625 V | 2.381 V |  |  |
| lab_opamp | v(in) | 1.563 V | 1.457 V to 1.672 V | 1.561 V |  |  |
| lab_opamp | v(out) | 3.125 V | 2.775 V to 3.508 V | 3.125 V |  |  |
<!-- lab-table:end -->

## Why measurements differ from the simulation

- **Part tolerances.** A 5 % resistor can be anywhere from 0.95 to 1.05 times its marked value.
  The tolerance range column shows the worst case those tolerances allow (computed with every
  part at the edge of its range).
- **Meter loading.** A digital multimeter on its volts range is roughly a 10 MΩ resistor. Across a
  1 MΩ resistor that is a big change (lab 2), and across a 4.7 kΩ resistor almost none (lab 1).
- **Supply voltage.** The simulation assumes exactly 5 V unless you change `VSUP`.
- **Models.** The diode and op-amp models are simplified. A real 1N4148's forward voltage
  depends on its exact batch, and a real op-amp's output can't quite reach the supply rails.
- **The meter.** A typical meter is accurate to about ±(0.5 % + 2 digits) on DC volts.
