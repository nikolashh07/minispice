"""Part G: simulation vs measurements, and the microcontroller link (with a fake serial port)."""

import pathlib

import pytest

from minispice import MiniSpiceError, load, parse
from minispice.__main__ import main
from minispice.hardware import HardwareLink, compare, comparison_table, parse_line, read_measurements, read_samples, write_samples

LAB = pathlib.Path(__file__).parent.parent / "examples" / "lab"


@pytest.mark.parametrize("path", sorted(LAB.glob("*.cir")), ids=lambda p: p.name)
def test_lab_circuits_solve(path):
    from minispice import operating_point
    from minispice.analysis.transient import run_settings, settings_from_directive

    circuit = load(str(path))
    if circuit.find_directives("tran"):
        result = run_settings(circuit, settings_from_directive(circuit.find_directives("tran")[0]))
        assert result.times[-1] == pytest.approx(0.2)
    else:
        operating_point(circuit)


def test_meter_loading_is_simulated():
    rows = compare(load(str(LAB / "lab_highz_divider.cir")), [("v(mid)", 2.38)])
    row = rows[0]
    assert row.simulated == pytest.approx(2.5)
    # 1 MΩ in parallel with a 10 MΩ meter is 909 kΩ: 5 V × 909k / 1.909M = 2.381 V.
    assert row.loaded == pytest.approx(5 * (1 / (1 / 1e6 + 1 / 10e6)) / (1e6 + 1 / (1 / 1e6 + 1 / 10e6)), rel=1e-6)
    assert "meter's own 10 MΩ" in row.explanation()


def test_tolerance_range_explains_a_small_difference():
    rows = compare(load(str(LAB / "lab_divider.cir")), [("v(mid)", 1.55)])
    row = rows[0]
    assert row.simulated == pytest.approx(5 * 4.7 / 14.7)
    assert row.low < 1.55 < row.high
    assert "Inside the" in row.explanation()


def test_reading_far_off_says_to_check_wiring():
    rows = compare(load(str(LAB / "lab_divider.cir")), [("v(mid)", 3.0)])
    assert "check the wiring" in rows[0].explanation()


def test_measurement_sheet(tmp_path):
    sheet = tmp_path / "m.csv"
    sheet.write_text("probe,measured\nv(mid),1.6\nv(vcc),\ni(R1),340u\n", encoding="utf-8")
    assert read_measurements(str(sheet)) == [("v(mid)", 1.6), ("i(R1)", pytest.approx(340e-6))]
    sheet.write_text("probe,measured\nv(mid),\n", encoding="utf-8")
    with pytest.raises(MiniSpiceError, match="no measurements yet"):
        read_measurements(str(sheet))


def test_compare_command(capsys, tmp_path):
    sheet = tmp_path / "m.csv"
    sheet.write_text("probe,measured\nv(mid),1.58\n", encoding="utf-8")
    assert main(["compare", str(LAB / "lab_divider.cir"), str(sheet)]) == 0
    out = capsys.readouterr().out
    assert "1.599 V" in out and "1.58 V" in out


def test_parse_line_matches_the_browser():
    assert parse_line("1500,1023,0") == (1.5, [5.0, 0.0])
    t, volts = parse_line("0,4095", vref=3.3, bits=12)
    assert volts == [pytest.approx(3.3)]
    assert parse_line("# MiniSpice probe ready") is None
    assert parse_line("12,abc") is None


class FakeSerial:
    """Stands in for pyserial: replays lines like the firmware would send."""

    def __init__(self, port, baud, timeout):
        self.lines = [b"# MiniSpice probe ready: 10-bit ADC, 5.00 V reference\r\n"]
        self.lines += [f"{1000 + k},{k * 10},{1023 - k * 10}\r\n".encode() for k in range(50)]
        self.closed = False

    def readline(self):
        return self.lines.pop(0) if self.lines else b"99999,0,0\r\n"

    def close(self):
        self.closed = True


def test_hardware_link_reads_and_saves(tmp_path):
    link = HardwareLink("COM9", serial_factory=FakeSerial)
    path = tmp_path / "samples.csv"
    count = write_samples(str(path), link.samples(0.02))
    link.close()
    assert count == 21  # samples at 0, 1, ..., 20 ms
    times, channels = read_samples(str(path))
    assert times[0] == 0 and times[-1] == pytest.approx(0.02)
    assert channels["a1"][0] == pytest.approx(5.0)
    assert link.port.closed


def test_bad_port_is_explained():
    def broken(*args, **kwargs):
        raise OSError("could not open port 'COM99'")

    with pytest.raises(MiniSpiceError, match="Check the port name"):
        HardwareLink("COM99", serial_factory=broken)


def test_overlay_command(capsys, tmp_path):
    samples = tmp_path / "rc.csv"
    write_samples(str(samples), ((k * 1e-3, [5.0 if (k // 10) % 2 == 0 else 0.0, 2.0]) for k in range(200)))
    out_png = tmp_path / "overlay.png"
    assert main(["overlay", str(LAB / "lab_rc.cir"), str(samples), "--probe", "v(cap)", "--channel", "a1", "--out", str(out_png)]) == 0
    assert out_png.read_bytes()[:4] == b"\x89PNG"
