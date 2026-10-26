"""Reading SPICE-style numbers (1k, 4.7u, 10meg) and printing results in engineering notation."""

import math
import re

_NUMBER = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Zµ%]*)$")

# Checked in this order so "meg" wins over "m". SPICE rule: M is milli, MEG is mega,
# so "1M" is one milli-ohm. Following the rule keeps netlists from other simulators correct.
_SUFFIXES = (
    ("meg", 1e6),
    ("t", 1e12),
    ("g", 1e9),
    ("k", 1e3),
    ("m", 1e-3),
    ("u", 1e-6),
    ("µ", 1e-6),
    ("n", 1e-9),
    ("p", 1e-12),
    ("f", 1e-15),
)


def parse_value(text):
    """Turn '4.7k', '1uF', '10meg', '5%' or '2.2e-3' into a float.

    Letters after the suffix are ignored, so '1kohm' and '10V' work. Raises ValueError
    with an example of valid input when the text is not a number.
    """
    match = _NUMBER.match(str(text).strip())
    if not match:
        raise ValueError(f"'{text}' is not a number (examples: 1k, 4.7u, 10meg, 2.2e-3)")
    number, letters = match.groups()
    value = float(number)
    letters = letters.lower()
    if letters.startswith("%"):
        return value / 100
    for suffix, scale in _SUFFIXES:
        if letters.startswith(suffix):
            return value * scale
    return value


def is_number(text):
    try:
        parse_value(text)
        return True
    except ValueError:
        return False


_PREFIXES = (
    (1e12, "T"),
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1.0, ""),
    (1e-3, "m"),
    (1e-6, "µ"),
    (1e-9, "n"),
    (1e-12, "p"),
    (1e-15, "f"),
)


def format_eng(value, unit="", digits=4):
    """Format a number like a datasheet: 1500 -> '1.5 kΩ', -0.005 -> '-5 mA'."""
    if value is None:
        return "-"
    if isinstance(value, complex):
        return f"{format_eng(abs(value), unit, digits)} ∠ {math.degrees(math.atan2(value.imag, value.real)):.1f}°"
    if math.isnan(value) or math.isinf(value):
        return f"{value} {unit}".strip()
    # Round first so 999.99996 becomes 1 k instead of 1000 (no prefix).
    value = float(f"{value:.{digits}g}")
    # Anything this small is numerical noise from the solver, not a real reading.
    if abs(value) < 5e-16:
        return f"0 {unit}".strip()
    for scale, prefix in _PREFIXES:
        if abs(value) >= scale:
            break
    mantissa = float(f"{value / scale:.{digits}g}")
    text = f"{mantissa:g}"
    return f"{text} {prefix}{unit}".strip()
