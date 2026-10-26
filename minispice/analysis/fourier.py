"""Fourier analysis: harmonics, THD and spectra of transient results.

Any repeating waveform is a sum of sine waves at the fundamental frequency and its multiples
(harmonics). The FFT is a fast way to find how much of each frequency a sampled signal contains,
the way a prism splits light into colors.
"""

from dataclasses import dataclass

import numpy as np

from ..errors import CircuitError


@dataclass
class FourierResult:
    fundamental: float
    dc: float
    harmonics: np.ndarray  # 1, 2, 3, ...
    frequencies: np.ndarray
    magnitudes: np.ndarray  # peak amplitude of each harmonic
    phases: np.ndarray  # degrees, relative to a cosine

    @property
    def thd(self):
        """Total harmonic distortion: the size of all harmonics 2..N relative to the fundamental."""
        if self.magnitudes[0] == 0:
            return float("inf")
        return float(np.sqrt(np.sum(self.magnitudes[1:] ** 2)) / self.magnitudes[0])

    def normalized(self):
        return self.magnitudes / self.magnitudes[0]


def fourier(times, values, fundamental, n_harmonics=9, periods=1, samples_per_period=1024):
    """Harmonics of a waveform over its last `periods` periods, like SPICE's .four."""
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)
    period = 1.0 / fundamental
    t_end = times[-1]
    t_begin = t_end - periods * period
    if t_begin < times[0] - 1e-12 * period:
        raise CircuitError(
            f"Fourier analysis at {fundamental:g} Hz needs at least {periods} full period(s) "
            f"({periods * period:g} s) of transient data, but the run is only {t_end - times[0]:g} s long."
        )
    n = samples_per_period * periods
    # Sample at the middle of each slot so a sample never sits exactly on a sharp edge.
    grid = t_begin + (np.arange(n) + 0.5) * (periods * period / n)
    samples = np.interp(grid, times, values)
    coeffs = np.fft.rfft(samples) / n
    # The half-sample offset adds a known phase shift to every bin; take it back out.
    bins = np.arange(len(coeffs))
    coeffs = coeffs * np.exp(-1j * np.pi * bins / n)
    harmonics = np.arange(1, n_harmonics + 1)
    picked = coeffs[harmonics * periods]
    return FourierResult(
        fundamental=fundamental,
        dc=float(coeffs[0].real),
        harmonics=harmonics,
        frequencies=harmonics * fundamental,
        magnitudes=2 * np.abs(picked),
        phases=np.degrees(np.angle(picked)),
    )


def spectrum(times, values, points=None, window=True):
    """One-sided amplitude spectrum of a transient waveform: (frequencies, peak amplitudes)."""
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)
    if points is None:
        points = 1 << int(np.ceil(np.log2(max(len(times), 256))))
    grid = np.linspace(times[0], times[-1], points, endpoint=False)
    samples = np.interp(grid, times, values)
    if window:
        # A Hann window stops the cut-off ends of the record from smearing energy across the spectrum.
        w = np.hanning(points)
        gain = w.sum()
    else:
        w = np.ones(points)
        gain = points
    coeffs = np.fft.rfft((samples - samples.mean()) * w) / gain
    amps = 2 * np.abs(coeffs)
    amps[0] = abs(samples.mean())
    freqs = np.fft.rfftfreq(points, d=grid[1] - grid[0])
    return freqs, amps
