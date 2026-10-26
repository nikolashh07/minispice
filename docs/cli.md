# Command line

```
python -m minispice <netlist> [analyses] [options]
```

With no analysis options, MiniSpice runs the analyses the netlist asks for (`.op`, `.tran`, `.ac`,
`.four`, `.dc`, `.noise`, `.mc`, `.sens`, with `.step` repeating them), or a DC operating point
if it asks for none.

## Analyses

| Option | Does |
|---|---|
| `--dc` (or `--op`) | DC operating point |
| `--tran [TSTEP TSTOP]` | Transient |
| `--ac [dec N F1 F2]` | AC sweep |
| `--four FREQ` | Fourier analysis of the transient |
| `--sweep NAME START STOP STEP` | DC sweep of a source, a part's value, or `temp` |
| `--thevenin A [B]`, `--norton A [B]`, `--max-power A [B]` | Equivalent circuits between nodes A and B (B defaults to ground) |
| `--superposition` | Each source's contribution to every node |
| `--mc RUNS` | Monte Carlo |
| `--worst-case` | Worst-case corners |
| `--sens EXPR` | Sensitivity ranking |
| `--noise OUTPUT [SOURCE]` | Noise analysis |
| `--explain [FILE]` | Step-by-step explanation (prints, or saves to .txt/.md/.tex/.pdf) |
| `--schematic FILE` | Draws the circuit with DC results (.svg or .png) |

## Options

| Option | Does |
|---|---|
| `--probe EXPR` | What to report or plot, repeatable: `--probe "v(out)" --probe "i(R1)"` |
| `--plot [DIR]` | Save plots as PNG (default folder `output`) |
| `--step PART V1 V2 ...` | Repeat the chosen analyses for each value |
| `--remove PART` | Remove a part (like a load) before a theorem analysis |
| `--temp DEG` | Circuit temperature in °C |
| `--method be\|trap`, `--fixed-step` | Transient integration settings |
| `--seed N`, `--gaussian` | Monte Carlo settings |
| `--plain-schematic` | Schematic without results |

## Other commands

| Command | Does |
|---|---|
| `python -m minispice check FILE` | Checks `* answer:` lines in a homework file |
| `python -m minispice practice [--level 1-4] [--seed N]` | Random circuits to solve by hand |
| `python -m minispice compare CIRCUIT READINGS.csv` | Simulation vs multimeter readings |
| `python -m minispice measure --port PORT [--seconds S]` | Records the probe firmware to CSV |
| `python -m minispice overlay CIRCUIT SAMPLES.csv --probe EXPR` | Plots measured over simulated |

Exit codes: 0 success, 1 circuit or netlist error (the message says what's wrong), 2 file not
found, 3 wrong homework answers.
