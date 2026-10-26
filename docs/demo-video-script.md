# Demo video script (2 minutes)

A shot list for a screen recording. Record at 1080p with the browser zoomed to 125 % so text is
readable on a phone. Talk over it, or add captions.

| Time | Show | Say |
|---|---|---|
| 0:00-0:10 | The web app with the LED example, current dots flowing | "This is MiniSpice, a circuit simulator I built in Python that runs right in the browser." |
| 0:10-0:30 | Place a resistor, wire it in parallel with R1, watch the dots and voltages update | "You draw a circuit and it solves it live, using Kirchhoff's laws. The dots are the current, and they move faster where there's more of it." |
| 0:30-0:45 | Drag the R1 slider; the LED's current changes and R1 turns red when it overheats | "Change a value and everything updates. It warns you when a part would overheat." |
| 0:45-1:05 | RC low-pass example: probe both nodes, Run the oscilloscope; then the Bode plotter | "There's an oscilloscope for waveforms over time, and a Bode plotter that finds the filter's cutoff, 159 hertz, exactly what the formula 1 over 2πRC gives." |
| 1:05-1:30 | Explain tab, stepping through 3-4 steps while parts highlight | "What I'm proudest of is explain mode. It shows every law it used, KCL at each node and the matrix it solved, like a tutor working the problem." |
| 1:30-1:45 | Terminal: `python -m minispice check examples/homework_example.cir` | "It can check homework too. Here it finds where the answer went wrong: the student forgot a resistor." |
| 1:45-1:55 | 3D breadboard view, rotating | "And it shows you how to build the circuit on a real breadboard." |
| 1:55-2:00 | GitHub page with the test badge | "It's open source, with about 300 tests. The link is in the description." |

Tips: hide the bookmarks bar, close other tabs, and do a practice run first so the Python engine is
already cached and loads instantly.
