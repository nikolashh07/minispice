# Netlist format

A netlist is a text file with one part or command per line. It follows SPICE, so most netlists
from textbooks and other simulators work as they are.

## Basics

- `*` at the start of a line makes it a comment. The first line, if it's a comment, is the title.
- `;` or ` $` starts a comment at the end of a line.
- A line starting with `+` continues the line before it.
- Node `0` (or `gnd`) is ground. Other nodes can be numbers or names: `1`, `in`, `out`, `vcc`.
- Names are case-insensitive, like SPICE: `R1` and `r1` are the same part, and `OUT` and `out`
  are the same node.
- Everything after `.end` is ignored.

## Numbers

| Suffix | Meaning | Example |
|---|---|---|
| `f` | 10⁻¹⁵ | `10f` |
| `p` | 10⁻¹² | `22p` |
| `n` | 10⁻⁹ | `4.7n` |
| `u` or `µ` | 10⁻⁶ | `1u` |
| `m` | 10⁻³ | `5m` |
| `k` | 10³ | `4.7k` |
| `meg` | 10⁶ | `1meg` |
| `g` | 10⁹ | `2g` |
| `t` | 10¹² | `1t` |

Letters after the suffix are ignored, so `1kohm`, `10V` and `1uF` all work. **`M` means milli, not
mega**, exactly as in SPICE: write `1meg` for a megohm. `5%` means 0.05.

## Parts

| Line | Part |
|---|---|
| `R<name> n+ n- <ohms> [tc1=] [tc2=] [tol=5%] [rating=<watts>]` | Resistor, optional temperature coefficients, tolerance and power rating |
| `C<name> n+ n- <farads> [ic=<volts>] [tol=]` | Capacitor |
| `L<name> n+ n- <henries> [ic=<amps>] [tol=]` | Inductor |
| `K<name> L1 L2 <k>` | Coupling between two inductors, 0 < k ≤ 1 |
| `T<name> p+ p- s+ s- <Np/Ns>` | Ideal transformer (in SPICE, T is a transmission line) |
| `S<name> n+ n- [ton=] [toff=] [ron=] [roff=]` | Switch, closed while ton ≤ t < toff |
| `V<name> n+ n- [DC] <volts> [AC <mag> [<phase>]] [waveform]` | Voltage source |
| `I<name> n+ n- [DC] <amps> [AC ...] [waveform]` | Current source, pushing current from n+ through itself to n- |
| `E<name> n+ n- c+ c- <gain>` | Voltage-controlled voltage source |
| `G<name> n+ n- c+ c- <siemens>` | Voltage-controlled current source |
| `F<name> n+ n- <Vsource> <gain>` | Current-controlled current source |
| `H<name> n+ n- <Vsource> <ohms>` | Current-controlled voltage source |
| `U<name> in+ in- out [model] [a=] [vpos=] [vneg=] [gbw=]` | Op-amp: ideal by default |
| `D<name> anode cathode [model] [area=]` | Diode, LED or Zener |
| `Q<name> c b e [substrate] <model>` | BJT |
| `M<name> d g s [body] <model> [w=] [l=]` | MOSFET |
| `X<name> nodes... <subcircuit> [param=value ...]` | Subcircuit instance |

### Waveforms (for transient analysis)

| Waveform | Parameters |
|---|---|
| `PULSE(v1 v2 delay rise fall width period)` | trapezoidal pulse train |
| `SIN(offset amplitude freq [delay damping phase])` | sine wave |
| `PWL(t1 v1 t2 v2 ...)` | straight lines between points |
| `EXP(v1 v2 td1 tau1 td2 tau2)` | exponential rise and fall |
| `STEP(v1 v2 [delay])` | ideal step (MiniSpice addition) |

### Built-in models

Use these model names without a `.model` line: diodes `d`, `1n4148`, `1n4001`, `zener5v1`,
`1n4733a`, `led_red`, `led_green`, `led_blue`; BJTs `npn`, `pnp`, `2n3904`, `2n3906`; MOSFETs
`nmos`, `pmos` (k = 1 mA/V², |Vt| = 1 V), `2n7000`; op-amps `opamp` (ideal), `lm741`, `tl081`.

## Commands

| Command | Meaning |
|---|---|
| `.op` | DC operating point |
| `.dc <source/part/temp> <start> <stop> <step>` | DC sweep |
| `.tran <tstep> <tstop> [tstart [tmax]] [uic] [fixed] [method=be]` | Transient |
| `.ac dec\|oct\|lin <points> <fstart> <fstop>` | AC sweep |
| `.four <freq> v(node) ...` | Fourier analysis of the transient |
| `.noise v(out) [input source] dec <points> <fstart> <fstop>` | Noise |
| `.step <part> list <v1> <v2> ...` or `.step <part> <start> <stop> <step>` | Repeat the analyses for several values |
| `.mc <runs> v(out) [seed=] [dist=gaussian]` | Monte Carlo |
| `.sens v(out)` | Sensitivity |
| `.temp <°C>` | Circuit temperature (default 27 °C) |
| `.ic v(node)=<volts> ...` | Initial node voltages for a transient |
| `.model <name> <D\|NPN\|PNP\|NMOS\|PMOS\|OPAMP>(param=value ...)` | Device model |
| `.subckt <name> <ports...> [params: p=default ...]` ... `.ends` | Subcircuit definition |
| `.param <name>=<value> ...` | Parameters, used as `{expression}` anywhere |
| `.include <file>` | Read another netlist file |
| `.end` | End of the netlist |

Lines other simulators use for output (`.print`, `.plot`, `.probe`, `.options`, `.control` ...
`.endc`) are skipped with a note.

## Probes

Results are read with probe expressions, in the netlist, on the command line, and in Python:
`v(out)`, `v(a,b)` (difference), `i(R1)` (current into R1's first terminal), `i(Q1,b)` (into a
named terminal), `p(R1)` (power absorbed), and for AC `vdb(out)` and `vp(out)` (degrees).
