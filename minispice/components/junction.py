"""PN-junction math shared by diodes and BJTs: the Shockley equation, temperature, and Newton limiting."""

import math

from ..context import T_NOMINAL_C, kelvin, thermal_voltage

# Above this many thermal voltages exp() is continued as a straight line, so a wild Newton guess
# like 50 V across a diode doesn't overflow to infinity.
MAX_EXP_ARG = 80.0


def safe_exp(u):
    """exp(u) and its derivative, continued linearly past MAX_EXP_ARG."""
    if u > MAX_EXP_ARG:
        e = math.exp(MAX_EXP_ARG)
        return e * (1 + u - MAX_EXP_ARG), e
    e = math.exp(u)
    return e, e


def saturation_current(i_s, celsius, n=1.0, eg=1.11, xti=3.0):
    """IS at temperature: it roughly doubles every 5 °C, which is why a diode's voltage falls as it heats."""
    t, t_nom = kelvin(celsius), kelvin(T_NOMINAL_C)
    vt = thermal_voltage(celsius)
    return i_s * (t / t_nom) ** (xti / n) * math.exp((t / t_nom - 1) * eg / (n * vt))


def critical_voltage(nvt, i_s):
    """Where the diode curve bends sharply; above it Newton steps must be limited."""
    return nvt * math.log(nvt / (math.sqrt(2) * i_s))


def pnjlim(v_new, v_old, nvt, v_crit):
    """SPICE's junction voltage limiting.

    The exponential is so steep that a full Newton step can jump to a voltage where exp() is
    astronomically large. Above v_crit the step is replaced by a logarithmic one, which follows
    the curve instead of its tangent. Returns (limited voltage, whether it was limited).
    """
    if v_new > v_crit and abs(v_new - v_old) > 2 * nvt:
        if v_old > 0:
            arg = 1 + (v_new - v_old) / nvt
            v_new = v_old + nvt * math.log(arg) if arg > 0 else v_crit
        else:
            v_new = nvt * math.log(v_new / nvt)
        return v_new, True
    return v_new, False


def limited_voltage(ctx, key, v_new, nvt, i_s):
    """Apply pnjlim against the voltage this junction used last iteration (kept in ctx.limits)."""
    if ctx.mode == "ac":
        return v_new
    v_old = ctx.limits.get(key, 0.0)
    v, limited = pnjlim(v_new, v_old, nvt, critical_voltage(nvt, i_s))
    if limited:
        ctx.limited = True
    ctx.limits[key] = v
    return v
