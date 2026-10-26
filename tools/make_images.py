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


# Later phases add their own images here.
EXTRA = []

if __name__ == "__main__":
    main()
