# Analyses

| Analysis | Command line | Netlist | Python |
|---|---|---|---|
| DC operating point | `--dc` | `.op` | `operating_point(circuit)` |
| Thevenin / Norton | `--thevenin A [B]`, `--norton A [B]` | | `theorems.thevenin(circuit, a, b, remove=[...])` |
| Superposition | `--superposition` | | `theorems.superposition(circuit)` |
| Maximum power transfer | `--max-power A [B]` | | `theorems.max_power_transfer(...)` |
| Transient | `--tran TSTEP TSTOP` | `.tran` | `analysis.transient.transient(circuit, tstop, tstep)` |
| AC sweep | `--ac dec N F1 F2` | `.ac` | `analysis.ac.ac_analysis(circuit, f1, f2, n)` |
| Fourier | `--four FREQ` | `.four` | `analysis.fourier.fourier(times, values, freq)` |
| DC sweep | `--sweep NAME START STOP STEP` | `.dc` | `analysis.sweep.dc_sweep(circuit, name, values)` |
| Parameter sweep | `--step PART V1 V2 ...` | `.step` | `analysis.sweep.parameter_sweep(...)` |
| Monte Carlo | `--mc RUNS --probe v(out)` | `.mc` | `analysis.montecarlo.monte_carlo(circuit, expr, runs)` |
| Worst case | `--worst-case --probe v(out)` | | `analysis.montecarlo.worst_case(circuit, expr)` |
| Sensitivity | `--sens v(out)` | `.sens` | `analysis.sensitivity.sensitivity(circuit, expr)` |
| Noise | `--noise v(out) [SOURCE]` | `.noise` | `analysis.noise.noise_analysis(circuit, out, source, ...)` |

## DC operating point

Capacitors are open circuits and inductors are short circuits. Linear circuits take one matrix
solve; circuits with diodes or transistors use Newton's method. If plain Newton fails, MiniSpice
retries with gmin stepping (every node briefly leaks to ground) and then source stepping (all
sources ramped up from zero).

Every part's power is reported, and the sum of all powers is checked against zero (Tellegen's
theorem). Resistors with a `rating=` get an overheating warning when they absorb more than it.

## Transient

The default is trapezoidal integration with adaptive time steps: each step is also taken as
two half steps, and the difference estimates the error. Steps shrink where signals change quickly
and grow where they don't, up to `tstep`. Source edges and switch times are always landed on
exactly, and the step right after an edge uses backward Euler to avoid trapezoidal "ringing".

`--method be` and `--fixed-step` (or `method=be` and `fixed` on the `.tran` line) give the
simpler textbook method, useful for seeing how step size affects accuracy.

## AC

Each frequency is one complex matrix solve. Nonlinear parts are replaced by their small-signal
model at the DC operating point. `corner_frequency("v(out)")` finds the −3 dB point.

## Tolerances, Monte Carlo and worst case

Add `tol=5%` to any R, C or L. Monte Carlo builds random copies within those tolerances (uniform, or
Gaussian with ±tol at 3σ). Worst case tries every corner when there are up to 10 toleranced parts,
otherwise it uses the sensitivities to pick the worst corner.

## Noise

Thermal noise (4kT/R) from every resistor, shot noise (2qI) from diodes and BJTs, and channel noise
(8kT·gm/3) from MOSFETs. Results are the output noise density in V/√Hz, the input-referred noise if
an input source is given, the total RMS noise over the band, and each part's share of the total.
