# How I built MiniSpice

*Draft write-up. The technical parts are accurate; the places marked [like this] are for your
own experiences, which make it worth reading. Edit it into your own voice before posting.*

## Why

[Why you started: a class, a homework problem a simulator couldn't explain, curiosity about how
SPICE works.] Every circuit simulator I'd used gave me numbers but never said *why*. I wanted
one that shows its work.

## The core idea: one matrix

Every linear circuit, however tangled, is one matrix equation. Each node gives a KCL equation;
each voltage source adds one unknown (its current) and one equation (its voltage). That's
modified nodal analysis, and it's the heart of SPICE, which has powered chip design since the 1970s.

The design decision that made the rest possible: **each component writes its own entries into the
matrix** (its "stamp"). The solver doesn't know what a resistor or a transistor is. Adding a
part means adding one class. By the end there were 16 part types and the solver had never changed.

## The hard parts

**Nonlinear parts.** Diodes and transistors follow exponential laws, so I used Newton's method:
replace each part with its tangent line, solve, and repeat. The first version blew up (e^1000)
on a simple diode circuit. The fix is the same trick real SPICE uses: limit how far the
junction voltage can jump in one step, following the curve instead of the tangent. [What
debugging that felt like.]

**Time.** Capacitors and inductors turn into "companion models", a resistor plus a current
source per time step. Backward Euler made a ringing RLC circuit die out far too fast, because it
loses a little energy every step. Trapezoidal integration fixed that but rang after sudden
jumps, so the step right after an edge uses backward Euler: another standard simulator trick I
had to rediscover.

**The browser.** The whole Python engine runs in the browser through Pyodide, inside a Web
Worker so long simulations don't freeze the page. Only JSON crosses between JavaScript and Python.

## Proving it's right

Every phase has a circuit I solved by hand, turned into an automated test: about 300 tests,
covering 88 % of the code. A few favourites:

- an RC circuit reaches 63.2 % after one time constant
- an underdamped RLC rings at exactly √(ω0² − α²)/2π
- an RC filter's total noise is √(kT/C) no matter what R is

[Results from the ngspice comparison and your breadboard measurements, from docs/lab.md.]

## What I'd do next

[Ideas: a better schematic layout, more device models, a mobile layout for the editor.]

## What I learned

[Your own list. Ideas: how SPICE works inside, numerical methods actually matter, writing tests
first saves time, explaining something is the best test of understanding it.]
