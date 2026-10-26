# Validation against ngspice

[ngspice](https://ngspice.sourceforge.io) is the open-source descendant of Berkeley SPICE, the
simulator the whole industry grew from. MiniSpice is checked against it in two ways.

## Automatic comparison

```
python tools/compare_ngspice.py
```

This needs ngspice installed and on the PATH. The tool:

1. runs every example circuit that uses only standard SPICE parts through both simulators,
2. writes MiniSpice's built-in models out as ordinary `.model` lines so both simulate the same devices,
3. compares every node voltage.

It writes the results table to `docs/ngspice_validation.md`. The test `tests/test_ngspice.py`
does the same comparison and fails if any node differs by more than 0.1 %; it is skipped on
machines without ngspice.

## Hand checks

Every phase of the project has a circuit solved by hand, and each one is an automated test:

| Check | Expected | Test |
|---|---|---|
| 1 mA into 2 kΩ | 2 V | `test_dc.py` |
| 10 V divider, two 1 kΩ | 5 V, 5 mA | `test_dc.py` |
| Divider power | 25 mW each, source −50 mW | `test_power_theorems.py` |
| Thevenin textbook problem | 4 V, 4 kΩ | `test_power_theorems.py` |
| RC after one time constant | 63.2 % | `test_transient.py` |
| Underdamped RLC ringing | √(ω0² − α²)/2π | `test_transient.py` |
| RC low-pass at 1/(2πRC) | −3 dB, −45° | `test_ac_fourier.py` |
| Square wave harmonics | 1, 1/3, 1/5 | `test_ac_fourier.py` |
| 10:1 transformer | 120 V → 12 V | `test_ac_fourier.py` |
| VCCS 0.01 S into 1 kΩ | 10 V | `test_active.py` |
| Inverting and non-inverting gain | −Rf/Rin, 1 + Rf/Rg | `test_active.py` |
| Diode with 5 V and 1 kΩ | 0.6-0.7 V, 4.3 mA | `test_semiconductors.py` |
| MOSFET saturation | ½k(Vgs − Vt)² | `test_semiconductors.py` |
| Diode temperature coefficient | about −2 mV/°C | `test_semiconductors.py` |
| 5 % divider Monte Carlo | within 4.75-5.25 V | `test_advanced.py` |
| 1 kΩ thermal noise | 4.07 nV/√Hz | `test_advanced.py` |
| RC total noise | √(kT/C) | `test_advanced.py` |
