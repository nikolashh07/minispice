"""Regenerate the plots used in the README and docs: python tools/make_images.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from minispice import load  # noqa: E402
from minispice.analysis.ac import ac_from_directive  # noqa: E402
from minispice.analysis.transient import run_settings, settings_from_directive  # noqa: E402
from minispice.plotting import plot_bode, plot_transient  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "docs", "images")


def example(name):
    return load(os.path.join(ROOT, "examples", name))


def transient_of(name):
    circuit = example(name)
    return circuit, run_settings(circuit, settings_from_directive(circuit.find_directives("tran")[0]))


def main():
    circuit, result = transient_of("rc_charge.cir")
    plot_transient(result, ["v(1)", "v(2)"], os.path.join(OUT, "rc_charge.png"), "RC charging (τ = 1 ms)")
    circuit, result = transient_of("rlc_ring.cir")
    plot_transient(result, ["v(3)"], os.path.join(OUT, "rlc_ring.png"), "Underdamped RLC step response")
    circuit = example("rc_lowpass.cir")
    plot_bode(ac_from_directive(circuit, circuit.find_directives("ac")[0]), "v(2)", os.path.join(OUT, "rc_lowpass_bode.png"),
              "RC low-pass filter (fc = 159 Hz)")
    for extra in EXTRA:
        extra()
    print(f"Images written to {os.path.abspath(OUT)}")


def schematics():
    from minispice import operating_point
    from minispice.schematic import draw_schematic

    for name, out in (("thevenin.cir", "schematic_thevenin.png"), ("bjt_bias.cir", "schematic_bjt.png")):
        circuit = example(name)
        draw_schematic(circuit, os.path.join(OUT, out), operating_point(circuit))


def explain_gif():
    """An animated walkthrough: each frame highlights the parts of one explain-mode step."""
    import tempfile
    import textwrap

    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter

    from minispice.explain import explain_dc
    from minispice.schematic import draw_schematic

    circuit = example("two_sources.cir")
    walkthrough, solution = explain_dc(circuit)
    steps = [s for s in walkthrough.steps if s.parts or s.title in ("Choose the unknowns", "Solve", "Check the power balance")]
    images = []
    with tempfile.TemporaryDirectory() as folder:
        for k, step in enumerate(steps):
            path = os.path.join(folder, f"frame{k}.png")
            draw_schematic(circuit, path, solution, highlight=step.parts)
            images.append(plt.imread(path))
    fig = plt.figure(figsize=(8, 6.5))
    picture = fig.add_axes([0.02, 0.38, 0.96, 0.6])
    words = fig.add_axes([0.04, 0.02, 0.92, 0.34])
    for ax in (picture, words):
        ax.axis("off")

    def frame(k):
        step = steps[k]
        picture.clear()
        picture.axis("off")
        picture.imshow(images[k])
        words.clear()
        words.axis("off")
        body = "\n".join(textwrap.fill(line.strip(), 95) for line in step.lines[:5])
        words.text(0, 1, f"Step {walkthrough.steps.index(step) + 1}: {step.title}  ({step.law})", fontsize=11, weight="bold", va="top")
        words.text(0, 0.82, body, fontsize=8.5, va="top", family="monospace")

    animation = FuncAnimation(fig, frame, frames=len(steps))
    animation.save(os.path.join(OUT, "explain.gif"), writer=PillowWriter(fps=0.6))
    plt.close(fig)


EXTRA = [schematics, explain_gif]

if __name__ == "__main__":
    main()
