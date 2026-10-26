"""Graphs: transient waveforms, Bode plots, spectra, sweeps, histograms. Each function saves a PNG and returns its path."""

import os

import matplotlib

matplotlib.use("Agg")  # draw to files; no window needed
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .units import format_eng  # noqa: E402


def _finish(fig, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def _unit(expr):
    kind = expr.strip().lower()[0]
    return {"v": "V", "i": "A", "p": "W"}.get(kind, "")


def plot_transient(result, probes, path, title="Transient analysis"):
    # Volts and milliamps on one axis would flatten one of them, so each unit gets its own panel.
    groups = {}
    for expr in probes:
        groups.setdefault(_unit(expr), []).append(expr)
    fig, axes = plt.subplots(len(groups), 1, figsize=(8, 3 + 1.8 * len(groups)), sharex=True, squeeze=False)
    for ax, (unit, exprs) in zip(axes[:, 0], groups.items()):
        for expr in exprs:
            ax.plot(result.times * 1e3, result.measure(expr), label=expr)
        ax.set_ylabel(unit or "value")
        ax.grid(True, alpha=0.3)
        ax.legend()
    axes[0, 0].set_title(title)
    axes[-1, 0].set_xlabel("time (ms)")
    return _finish(fig, path)


def plot_bode(result, probe, path, title=None):
    """Magnitude in dB and phase in degrees against log frequency."""
    from .analysis.ac import db, phase_degrees

    value = result.measure(probe)
    fig, (mag, ph) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    mag.semilogx(result.freqs, db(value))
    mag.set_ylabel("magnitude (dB)")
    mag.set_title(title or f"Bode plot of {probe}")
    mag.grid(True, which="both", alpha=0.3)
    ph.semilogx(result.freqs, phase_degrees(value))
    ph.set_ylabel("phase (°)")
    ph.set_xlabel("frequency (Hz)")
    ph.grid(True, which="both", alpha=0.3)
    return _finish(fig, path)


def plot_spectrum(freqs, amplitudes, path, title="Spectrum", max_freq=None):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    keep = slice(None) if max_freq is None else freqs <= max_freq
    ax.plot(freqs[keep], amplitudes[keep])
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("amplitude")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    return _finish(fig, path)


def plot_harmonics(fourier_result, path, title="Harmonics"):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(fourier_result.harmonics, fourier_result.magnitudes, width=0.6)
    ax.set_xlabel(f"harmonic (× {format_eng(fourier_result.fundamental, 'Hz')})")
    ax.set_ylabel("amplitude")
    ax.set_title(f"{title} (THD {fourier_result.thd * 100:.2f} %)")
    ax.set_xticks(fourier_result.harmonics)
    ax.grid(True, axis="y", alpha=0.3)
    return _finish(fig, path)


def plot_sweep(x, curves, path, xlabel, title="DC sweep", ylabel=None):
    """curves: {label: y values}"""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for label, y in curves.items():
        ax.plot(x, y, label=label)
    ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    return _finish(fig, path)


def plot_histogram(values, path, label, title="Monte Carlo", limits=None):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(values, bins=30, edgecolor="white")
    if limits:
        for limit in limits:
            ax.axvline(limit, color="red", linestyle="--")
    ax.set_xlabel(label)
    ax.set_ylabel("runs")
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.3)
    return _finish(fig, path)


def plot_noise(freqs, density, path, title="Output noise"):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.loglog(freqs, density)
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("noise density (V/√Hz)")
    ax.set_title(title)
    ax.grid(True, which="both", alpha=0.3)
    return _finish(fig, path)


def plot_overlay(times_sim, sim, times_meas, measured, path, label, title="Simulation vs measurement"):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(np.asarray(times_sim) * 1e3, sim, label=f"simulated {label}")
    ax.plot(np.asarray(times_meas) * 1e3, measured, ".", markersize=3, label=f"measured {label}")
    ax.set_xlabel("time (ms)")
    ax.set_ylabel("V")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    return _finish(fig, path)
