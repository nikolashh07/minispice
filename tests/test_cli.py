import pathlib

from minispice.__main__ import main

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"


def run(capsys, *args):
    code = main([str(a) for a in args])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_dc_divider(capsys):
    code, out, _ = run(capsys, EXAMPLES / "divider.cir", "--dc")
    assert code == 0
    assert "5 V" in out
    assert "-5 mA" in out
    assert "balanced" in out


def test_runs_netlist_directives_by_default(capsys):
    code, out, _ = run(capsys, EXAMPLES / "divider.cir")
    assert code == 0
    assert "DC operating point" in out


def test_thevenin_option(capsys):
    code, out, _ = run(capsys, EXAMPLES / "thevenin.cir", "--thevenin", "3", "--remove", "RL")
    assert code == 0
    assert "4 V" in out and "4 kΩ" in out


def test_max_power_and_superposition(capsys):
    code, out, _ = run(capsys, EXAMPLES / "thevenin.cir", "--max-power", "3", "--remove", "RL")
    assert code == 0 and "1 mW" in out
    code, out, _ = run(capsys, EXAMPLES / "two_sources.cir", "--superposition")
    assert code == 0 and "V1 only" in out and "V2 only" in out


def test_errors_go_to_stderr(capsys, tmp_path):
    bad = tmp_path / "bad.cir"
    bad.write_text("V1 1 0 5\nR1 1 2\n")
    code, _, err = run(capsys, bad)
    assert code == 1
    assert "line 2" in err
    code, _, err = run(capsys, tmp_path / "missing.cir")
    assert code == 2
