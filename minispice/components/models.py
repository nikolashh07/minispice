"""Device models (.model lines) and a small built-in library of common parts."""

from dataclasses import dataclass, field

from .base import ParseError


@dataclass
class Model:
    name: str
    type: str  # d, npn, pnp, nmos, pmos, opamp
    params: dict = field(default_factory=dict)

    def get(self, key, default):
        return self.params.get(key, default)


# Parameter values are approximations of typical datasheet parts, good enough for coursework.
BUILTIN_MODELS = {
    m.name: m
    for m in [
        Model("d", "d", {}),
        Model("1n4148", "d", {"is": 2.52e-9, "n": 1.752, "rs": 0.568, "bv": 100, "ibv": 100e-6}),
        Model("1n4001", "d", {"is": 14.11e-9, "n": 1.984, "rs": 33.89e-3, "bv": 50, "ibv": 10e-6}),
        Model("zener5v1", "d", {"is": 1e-14, "n": 1, "rs": 1.0, "bv": 5.1, "ibv": 1e-3}),
        Model("1n4733a", "d", {"is": 1e-14, "n": 1, "rs": 1.0, "bv": 5.1, "ibv": 1e-3}),
        # LEDs are diodes with a wider band gap, so they turn on at a higher voltage.
        Model("led_red", "d", {"is": 1e-17, "n": 2.0, "rs": 2.0, "eg": 1.9}),
        Model("led_green", "d", {"is": 2.3e-20, "n": 2.0, "rs": 2.0, "eg": 2.2}),
        Model("led_blue", "d", {"is": 7e-23, "n": 2.5, "rs": 3.0, "eg": 2.7}),
        Model("npn", "npn", {}),
        Model("pnp", "pnp", {}),
        Model("2n3904", "npn", {"is": 6.734e-15, "bf": 416.4, "br": 0.7371, "vaf": 74.03}),
        Model("2n3906", "pnp", {"is": 1.41e-15, "bf": 180.7, "br": 4.977, "vaf": 18.7}),
        Model("nmos", "nmos", {}),
        Model("pmos", "pmos", {}),
        Model("2n7000", "nmos", {"vto": 1.6, "kp": 0.1}),
        Model("opamp", "opamp", {}),
        Model("lm741", "opamp", {"a": 200e3, "gbw": 1e6, "vpos": 15, "vneg": -15}),
        Model("tl081", "opamp", {"a": 200e3, "gbw": 3e6, "vpos": 15, "vneg": -15}),
    ]
}

MODEL_TYPES = ("d", "npn", "pnp", "nmos", "pmos", "opamp")


def find_model(models, name, allowed_types, part):
    """Look up a model by name: the netlist's .model lines first, then the built-in library."""
    model = models.get(name.lower()) or BUILTIN_MODELS.get(name.lower())
    if model is None:
        builtin = ", ".join(m.name for m in BUILTIN_MODELS.values() if m.type in allowed_types)
        raise ParseError(f"{part} uses model '{name}', which isn't defined. Add a .model line, or use a built-in model: {builtin}")
    if model.type not in allowed_types:
        raise ParseError(f"{part} needs a {' or '.join(t.upper() for t in allowed_types)} model, but '{name}' is a {model.type.upper()} model")
    return model


def is_model_name(models, name, allowed_types):
    model = models.get(name.lower()) or BUILTIN_MODELS.get(name.lower())
    return model is not None and model.type in allowed_types
