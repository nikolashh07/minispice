# Explain mode and homework

## Explain mode

```
python -m minispice examples/two_sources.cir --explain
python -m minispice examples/two_sources.cir --explain solution.pdf
```

The walkthrough has these steps:

1. **Choose the unknowns:** the node voltages, plus the current of every voltage source (that
   extra unknown is what makes nodal analysis "modified").
2. **What each part contributes:** the law behind each part's stamp, such as Ohm's law for a
   resistor, KVL for a voltage source, the Shockley equation for a diode, or the virtual short for an ideal op-amp.
3. **KCL at every node**, written as an equation and then checked with the final numbers.
4. **KVL for every voltage source.**
5. **The matrix** A·x = b, for circuits small enough to read.
6. **The solution**, and for nonlinear circuits how Newton's method got there.
7. **Current and power in every part**, with Ohm's law worked out for each resistor.
8. **The power balance**, confirming energy is conserved.

Each step lists the parts it's about, which the web app uses to highlight them.

## Homework checker

Put your answers in the circuit file, in the order you worked them out:

```
* Homework example
V1 1 0 12
R1 1 2 6k
R2 2 0 3k
R3 2 0 6k
* answer: i(R1) = 1.5m
* answer: v(2) = 4
```

```
python -m minispice check examples/homework_example.cir
```

```
1. i(R1) = 1.5 mA: right
2. v(2) = 4 V: WRONG

Your work first goes wrong at v(2): you have 4 V, but it should be 3 V.
Your answer is what you'd get if you left R3 out (as if it were an open circuit). Check how R3 is connected.
```

To find the mistake, MiniSpice tests what common slips would have produced:
- a flipped sign
- an answer 1000 or a million times off
- each resistor left out
- each resistor replaced by a wire

## Practice mode

```
python -m minispice practice --level 2
```

It generates a random circuit with resistor values that combine into round numbers, asks for a
few quantities, checks the answers, and shows the full walkthrough if any are wrong. The levels:

| Level | Circuit |
|---|---|
| 1 | a voltage divider |
| 2 | series-parallel resistors |
| 3 | two voltage sources |
| 4 | a current source ladder |

`--seed` repeats a problem, so a class can all work on the same one.
