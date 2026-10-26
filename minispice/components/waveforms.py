"""Time-varying source shapes for transient analysis, using the standard SPICE parameter order."""

import math

from .base import ParseError

WAVEFORM_NAMES = ("pulse", "sin", "pwl", "exp", "step")


class Waveform:
    name = ""

    def value(self, t):
        raise NotImplementedError

    def breakpoints(self, t_stop):
        return []

    def spec(self):
        raise NotImplementedError


def _fill(values, count, defaults, keyword):
    if len(values) > count:
        raise ParseError(f"{keyword.upper()} takes at most {count} numbers, got {len(values)}")
    return list(values) + list(defaults[len(values):])


class Pulse(Waveform):
    """PULSE(v1 v2 delay rise fall width period): a trapezoid that repeats every period."""

    name = "pulse"

    def __init__(self, values):
        if len(values) < 2:
            raise ParseError("PULSE needs at least two values: PULSE(v1 v2 [delay rise fall width period])")
        v1, v2, td, tr, tf, pw, per = _fill(values, 7, [0, 0, 0, 0, 0, math.inf, math.inf], "pulse")
        self.v1, self.v2, self.td, self.tr, self.tf, self.pw, self.per = v1, v2, td, tr, tf, pw, per

    def value(self, t):
        if t <= self.td:
            return self.v1
        t = t - self.td
        if math.isfinite(self.per) and self.per > 0:
            t = math.fmod(t, self.per)
        if t < self.tr:
            return self.v1 + (self.v2 - self.v1) * t / self.tr
        t -= self.tr
        if t <= self.pw:
            return self.v2
        t -= self.pw
        if t < self.tf:
            return self.v2 + (self.v1 - self.v2) * t / self.tf
        return self.v1

    def breakpoints(self, t_stop):
        points = []
        start = self.td
        while start < t_stop:
            for offset in (0, self.tr, self.tr + self.pw, self.tr + self.pw + self.tf):
                if math.isfinite(offset):
                    points.append(start + offset)
            if not (math.isfinite(self.per) and self.per > 0):
                break
            start += self.per
        return points

    def spec(self):
        return "PULSE(" + " ".join(f"{v:g}" for v in (self.v1, self.v2, self.td, self.tr, self.tf, self.pw, self.per) if math.isfinite(v)) + ")"


class Sine(Waveform):
    """SIN(offset amplitude freq delay damping phase_degrees)."""

    name = "sin"

    def __init__(self, values):
        if len(values) < 3:
            raise ParseError("SIN needs at least offset, amplitude and frequency: SIN(vo va freq [delay damping phase])")
        self.vo, self.va, self.freq, self.td, self.theta, self.phase = _fill(values, 6, [0, 0, 0, 0, 0, 0], "sin")

    def value(self, t):
        phase = math.radians(self.phase)
        if t <= self.td:
            return self.vo + self.va * math.sin(phase)
        t = t - self.td
        return self.vo + self.va * math.exp(-self.theta * t) * math.sin(2 * math.pi * self.freq * t + phase)

    def breakpoints(self, t_stop):
        return [self.td] if self.td > 0 else []

    def spec(self):
        return f"SIN({self.vo:g} {self.va:g} {self.freq:g} {self.td:g} {self.theta:g} {self.phase:g})"


class PiecewiseLinear(Waveform):
    """PWL(t1 v1 t2 v2 ...): straight lines between the given points, flat after the last one."""

    name = "pwl"

    def __init__(self, values):
        if len(values) < 2 or len(values) % 2:
            raise ParseError("PWL needs pairs of time and value: PWL(t1 v1 t2 v2 ...)")
        self.times = values[0::2]
        self.values = values[1::2]
        if any(b < a for a, b in zip(self.times, self.times[1:])):
            raise ParseError("PWL times must not go backwards")

    def value(self, t):
        if t <= self.times[0]:
            return self.values[0]
        for (t0, v0), (t1, v1) in zip(zip(self.times, self.values), zip(self.times[1:], self.values[1:])):
            if t <= t1:
                if t1 == t0:
                    return v1
                return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
        return self.values[-1]

    def breakpoints(self, t_stop):
        return list(self.times)

    def spec(self):
        return "PWL(" + " ".join(f"{t:g} {v:g}" for t, v in zip(self.times, self.values)) + ")"


class Exponential(Waveform):
    """EXP(v1 v2 delay1 tau1 delay2 tau2): exponential rise to v2, then decay back to v1."""

    name = "exp"

    def __init__(self, values):
        if len(values) < 2:
            raise ParseError("EXP needs at least v1 and v2: EXP(v1 v2 [td1 tau1 td2 tau2])")
        self.v1, self.v2, self.td1, self.tau1, self.td2, self.tau2 = _fill(values, 6, [0, 0, 0, 1e-9, math.inf, 1e-9], "exp")

    def value(self, t):
        v = self.v1
        if t > self.td1:
            v += (self.v2 - self.v1) * (1 - math.exp(-(t - self.td1) / self.tau1))
        if t > self.td2:
            v += (self.v1 - self.v2) * (1 - math.exp(-(t - self.td2) / self.tau2))
        return v

    def breakpoints(self, t_stop):
        return [t for t in (self.td1, self.td2) if math.isfinite(t)]

    def spec(self):
        return f"EXP({self.v1:g} {self.v2:g} {self.td1:g} {self.tau1:g} {self.td2:g} {self.tau2:g})"


class Step(Waveform):
    """STEP(v1 v2 delay): MiniSpice shorthand for an ideal step from v1 to v2 at the delay time."""

    name = "step"

    def __init__(self, values):
        if len(values) < 2:
            raise ParseError("STEP needs two values: STEP(v1 v2 [delay])")
        self.v1, self.v2, self.td = _fill(values, 3, [0, 0, 0], "step")

    def value(self, t):
        return self.v1 if t <= self.td else self.v2

    def breakpoints(self, t_stop):
        return [self.td]

    def spec(self):
        return f"STEP({self.v1:g} {self.v2:g} {self.td:g})"


WAVEFORMS = {"pulse": Pulse, "sin": Sine, "pwl": PiecewiseLinear, "exp": Exponential, "step": Step}
