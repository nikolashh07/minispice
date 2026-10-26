"""Talks to real circuits: compares measurements with simulation, and reads a microcontroller.

Simulation vs reality (Phase 33)
    Measure your breadboard with a multimeter, write the readings in a small CSV file:

        probe,measured
        v(2),4.93
        i(R1),4.95m

    and `python -m minispice compare circuit.cir readings.csv` lists simulated vs measured values.
    For each difference it checks the two usual suspects by simulating them:
      * part tolerances: is the reading inside the worst-case range the tol= values allow?
      * meter loading: a real voltmeter is a ~10 MΩ resistor; how much does adding it change the node?

Live hardware link (Phase 34)
    The firmware in firmware/minispice_probe prints one line per sample, "t_ms,a0,a1,a2,a3", over
    USB. `python -m minispice measure --port COM3` records them to CSV (pyserial needed), and
    `python -m minispice overlay circuit.cir samples.csv` plots them on top of the simulation.
"""

import csv
from dataclasses import dataclass

from .analysis.dc import operating_point
from .components.resistor import Resistor
from .errors import MiniSpiceError
from .results import parse_probe
from .units import format_eng, parse_value

METER_RESISTANCE = 10e6  # input resistance of a typical digital multimeter on its volts range


# ---- simulation vs measurement ---------------------------------------------------------------------

def read_measurements(path):
    """[(probe, value)] from a CSV with 'probe' and 'measured' columns. Blank readings are skipped."""
    rows = []
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            probe = (row.get("probe") or "").strip()
            text = (row.get("measured") or "").strip()
            if not probe or not text:
                continue
            try:
                rows.append((probe, parse_value(text)))
            except ValueError:
                raise MiniSpiceError(f"{path}: can't read the measurement '{text}' for {probe}") from None
    if not rows:
        raise MiniSpiceError(f"{path} has no measurements yet. Fill in the 'measured' column.")
    return rows


@dataclass
class Comparison:
    probe: str
    simulated: float
    measured: float
    low: float = None  # worst-case range from part tolerances
    high: float = None
    loaded: float = None  # simulated value with a voltmeter attached

    @property
    def error_percent(self):
        if self.simulated == 0:
            return float("inf") if self.measured else 0.0
        return 100 * (self.measured - self.simulated) / abs(self.simulated)

    def explanation(self):
        unit = {"v": "V", "i": "A", "p": "W"}.get(self.probe.lower()[0], "")
        reasons = []
        if abs(self.error_percent) <= 1:
            return "Within 1 %: as good as the parts and the meter allow."
        if self.low is not None and self.low <= self.measured <= self.high:
            reasons.append(f"inside the {format_eng(self.low, unit)} to {format_eng(self.high, unit)} range the part tolerances allow")
        elif self.low is not None:
            reasons.append(f"outside the {format_eng(self.low, unit)} to {format_eng(self.high, unit)} tolerance range, "
                           "so check the wiring and the part values")
        if self.loaded is not None and abs(self.loaded - self.simulated) > 0.002 * abs(self.simulated):
            reasons.append(f"the meter's own {format_eng(METER_RESISTANCE, 'Ω')} pulls this node to about {format_eng(self.loaded, unit)}")
        if not reasons:
            reasons.append("bigger than tolerances or meter loading explain: check the wiring, the supply voltage and the meter's range")
        text = "; ".join(reasons)
        return text[0].upper() + text[1:] + "."


def compare(circuit, measurements, meter_resistance=METER_RESISTANCE):
    """Simulated vs measured for each probe, with tolerance ranges and meter loading worked out."""
    nominal = operating_point(circuit)
    has_tolerances = any(c.tol for c in circuit.components)
    out = []
    for probe, measured in measurements:
        row = Comparison(probe, nominal.measure(probe), measured)
        if has_tolerances:
            from .analysis.montecarlo import worst_case

            wc = worst_case(circuit, probe)
            row.low, row.high = wc.low, wc.high
        kind, node, ref = parse_probe(probe)
        if kind == "v" and meter_resistance:
            loaded = circuit.copy()
            loaded.add(Resistor("R_meter_", node, ref, meter_resistance))
            row.loaded = operating_point(loaded).measure(probe)
        out.append(row)
    return out


def comparison_table(rows):
    from .report import table

    lines = []
    for r in rows:
        unit = {"v": "V", "i": "A", "p": "W"}.get(r.probe.lower()[0], "")
        lines.append((r.probe, format_eng(r.simulated, unit), format_eng(r.measured, unit), f"{r.error_percent:+.2f} %"))
    text = table(["Quantity", "Simulated", "Measured", "Difference"], lines)
    text += "\n\n" + "\n".join(f"{r.probe}: {r.explanation()}" for r in rows)
    return text


# ---- the microcontroller link -----------------------------------------------------------------------

def parse_line(line, vref=5.0, bits=10):
    """'1500,1023,0' -> (1.5, [5.0, 0.0]). Lines that aren't samples (like the '#' banner) give None."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    try:
        fields = [float(v) for v in line.split(",")]
    except ValueError:
        return None
    if len(fields) < 2:
        return None
    full_scale = 2 ** bits - 1
    return fields[0] / 1000.0, [counts / full_scale * vref for counts in fields[1:]]


class HardwareLink:
    """Reads samples from the MiniSpice probe firmware over a serial port."""

    def __init__(self, port, baud=115200, vref=5.0, bits=10, serial_factory=None):
        self.vref, self.bits = vref, bits
        if serial_factory is None:
            try:
                import serial
            except ImportError:
                raise MiniSpiceError("Reading a board needs the pyserial library: pip install pyserial") from None
            serial_factory = serial.Serial
        try:
            self.port = serial_factory(port, baud, timeout=1)
        except Exception as error:  # pyserial raises SerialException; keep the message readable
            raise MiniSpiceError(f"Couldn't open {port}: {error}. Check the port name (Device Manager on Windows, "
                                 "ls /dev/tty* on Mac and Linux) and that no other program, like the Arduino serial monitor, has it open.") from None

    def samples(self, seconds):
        """Yield (time, [volts...]) for `seconds` of board time."""
        start = None
        while True:
            raw = self.port.readline()
            if not raw:
                continue
            sample = parse_line(raw.decode("ascii", errors="ignore"), self.vref, self.bits)
            if sample is None:
                continue
            if start is None:
                start = sample[0]
            if sample[0] - start > seconds + 1e-9:  # tolerance for millisecond times stored as floats
                return
            yield sample[0] - start, sample[1]

    def close(self):
        self.port.close()


def write_samples(path, samples):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        count = 0
        for t, volts in samples:
            if count == 0:
                writer.writerow(["t"] + [f"a{k}" for k in range(len(volts))])
            writer.writerow([f"{t:.6f}"] + [f"{v:.5f}" for v in volts])
            count += 1
    return count


def read_samples(path):
    """(times, {channel name: values}) from a CSV written by write_samples."""
    times, channels = [], {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            times.append(float(row["t"]))
            for key, value in row.items():
                if key != "t":
                    channels.setdefault(key, []).append(float(value))
    return times, channels
