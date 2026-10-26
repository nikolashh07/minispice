# How it works

## Modified nodal analysis

Every circuit becomes a matrix equation **A x = b**.

- The unknowns **x** are the voltage of every node except ground, plus the current through every
  part that fixes a voltage (voltage sources, inductors, controlled voltage sources, op-amp outputs).
- Each node gives one equation, KCL: the currents leaving the node add up to zero.
- Each voltage-fixing part gives one more equation, its own KVL relation, like V(1) − V(0) = 10.

The divider `V1 1 0 10`, `R1 1 2 1k`, `R2 2 0 1k` gives:

```
[ 1/1k   -1/1k    1 ] [ V(1)  ]   [  0 ]
[ -1/1k   2/1k    0 ] [ V(2)  ] = [  0 ]
[ 1       0       0 ] [ I(V1) ]   [ 10 ]
```

## Stamps

No file in the solver knows what a resistor is. Each component class has a `stamp()` method that
adds its own numbers to the matrix. A resistor between nodes a and b adds `+G` to (a,a) and (b,b)
and `−G` to (a,b) and (b,a). A voltage source adds ±1 entries linking its nodes to its current.
Adding a new kind of part means writing one class; the solver never changes.

Each stamp can also leave a sentence for explain mode, such as "R1 adds a conductance of 1 mS to
the KCL equations of nodes 1 and 2". The walkthroughs are built from those sentences.

## Newton's method

A diode's current is exponential in its voltage, so its equation isn't linear. MiniSpice guesses
the voltages, replaces each nonlinear part with its tangent line at the guess (a conductance plus
a current source), solves the now-linear matrix, and repeats until the answer stops changing.

The exponential is so steep that a raw Newton step can ask for e^1000. SPICE's junction limiting
(`pnjlim`) replaces such a step with a logarithmic one that follows the curve, and MOSFETs have
similar limits on Vgs and Vds. If Newton still fails, gmin stepping and source stepping take over.

## Companion models

In a transient, every time step turns each capacitor into a resistor in parallel with a current
source that reproduces i = C dv/dt over that step:

| Method | Conductance | History current |
|---|---|---|
| Backward Euler | C/h | (C/h)·v_prev |
| Trapezoidal | 2C/h | (2C/h)·v_prev + i_prev |

Inductors keep their current as a matrix unknown and use the same idea on v = L di/dt. Coupled
inductors add M terms between the two inductors' rows.

## AC: complex numbers

A sine wave at one frequency is a phasor, and d/dt becomes multiplication by jω. Capacitors
become admittances jωC and inductors impedances jωL, and the same stamping code fills a complex
matrix, solved once per frequency.

## Noise: the adjoint trick

Every resistor and junction is a random noise current. The output noise needs the transfer
function from each of them to the output. Instead of one solve per source, MiniSpice solves the
*transposed* matrix once per frequency with a 1 at the output. Entry k of that answer is the
transfer from a current injected at node k, for every k at once.

## Sparse matrices

A circuit's matrix is almost all zeros: each part touches two or three nodes. Above 150 unknowns
MiniSpice collects stamps as (row, column, value) triplets and solves with scipy's sparse solver,
which makes a 10,000-node circuit take well under a second ([benchmarks](benchmarks.md)).
