import pytest

from minispice import NetlistError, parse, parse_value
from minispice.units import format_eng


# ---- values -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("1k", 1e3), ("4.7u", 4.7e-6), ("10meg", 10e6), ("10MEG", 10e6), ("2.2e-3", 2.2e-3),
    ("1p", 1e-12), ("3n", 3e-9), ("5m", 5e-3), ("1g", 1e9), ("-2.5", -2.5), (".5k", 500),
    ("1kohm", 1e3), ("10V", 10), ("1uF", 1e-6), ("5%", 0.05),
])
def test_parse_value(text, expected):
    assert parse_value(text) == pytest.approx(expected)


def test_capital_m_is_milli_like_spice():
    # The SPICE rule: 1M is one milli-ohm, not one megohm.
    assert parse_value("1M") == pytest.approx(1e-3)


@pytest.mark.parametrize("text", ["abc", "k1", "", "1..2"])
def test_parse_value_rejects_non_numbers(text):
    with pytest.raises(ValueError):
        parse_value(text)


@pytest.mark.parametrize("value, unit, expected", [
    (5, "V", "5 V"), (-0.005, "A", "-5 mA"), (1500, "Ω", "1.5 kΩ"), (0, "W", "0 W"),
    (0.99999996, "V", "1 V"), (4.7e-6, "F", "4.7 µF"), (1e-20, "A", "0 A"), (2.5e6, "Hz", "2.5 MHz"),
])
def test_format_eng(value, unit, expected):
    assert format_eng(value, unit) == expected


# ---- netlists -----------------------------------------------------------------------------------

def test_hand_check_resistor():
    """Phase 1 hand check: R1 parses as 1000 Ω between nodes 1 and 2."""
    circuit = parse("* comment\nV1 1 0 DC 10\nR1 1 2 1k\nR2 2 0 1k\n")
    r1 = circuit.get("R1")
    assert r1.value == 1000
    assert r1.nodes == ["1", "2"]
    assert len(circuit.components) == 3


def test_first_comment_becomes_title():
    assert parse("* My divider\nR1 1 0 1k\nV1 1 0 1").title == "My divider"


def test_spice_title_line():
    circuit = parse("RC low pass filter\nR1 1 0 1k\nV1 1 0 1")
    assert circuit.title == "RC low pass filter"
    assert len(circuit.components) == 2


def test_names_and_nodes_are_case_insensitive():
    circuit = parse("V1 IN gnd 5\nr1 In OUT 1k\nR2 out 0 1k")
    assert circuit.get("R1") is circuit.get("r1")
    assert circuit.get("V1").nodes == ["in", "0"]
    assert circuit.nodes == ["in", "out"]


def test_duplicate_names_are_an_error():
    with pytest.raises(NetlistError, match="defined twice"):
        parse("R1 1 0 1k\nr1 1 0 2k\nV1 1 0 1")


def test_dc_keyword_is_optional():
    assert parse("V1 1 0 10\nR1 1 0 1").get("V1").value == 10
    assert parse("V1 1 0 DC 10\nR1 1 0 1").get("V1").value == 10


def test_comments_blank_lines_and_continuations():
    circuit = parse("""
* a comment

V1 1 0 DC 5 ; inline comment
R1 1
+ 0 2k
.end
R9 1 0 1k
""")
    assert circuit.get("R1").value == 2000
    assert not circuit.has("R9")  # everything after .end is ignored


def test_every_problem_is_reported_with_line_numbers():
    with pytest.raises(NetlistError) as info:
        parse("V1 1 0 DC 10\nR1 1 2\nR2 2 0 abc\nZ1 1 0 5\n.bogus")
    problems = info.value.problems
    assert [where for where, _ in problems] == ["line 2", "line 3", "line 4", "line 5"]
    message = str(info.value)
    assert "R1 has no resistance" in message
    assert "'abc' is not a number" in message
    assert "no component type starts with 'Z'" in message
    assert "Unknown command .bogus" in message


def test_zero_ohm_resistor_explains_alternative():
    with pytest.raises(NetlistError, match="0 V voltage source"):
        parse("R1 1 0 0\nV1 1 0 1")


def test_params_and_expressions():
    circuit = parse(".param rbase=1k gain=3\nR1 1 0 {rbase*gain}\nR2 1 2 {2*rbase + 500}\nV1 2 0 1")
    assert circuit.get("R1").value == 3000
    assert circuit.get("R2").value == 2500


def test_unknown_param_is_an_error():
    with pytest.raises(NetlistError, match="not a defined .param"):
        parse("R1 1 0 {nope}\nV1 1 0 1")


def test_resistor_options():
    r = parse("R1 1 0 1k tol=5% rating=0.25 tc1=0.004\nV1 1 0 1").get("R1")
    assert (r.tol, r.rating, r.tc1) == (0.05, 0.25, 0.004)


def test_include(tmp_path):
    (tmp_path / "parts.inc").write_text("R2 2 0 1k\n")
    main = tmp_path / "main.cir"
    main.write_text("* main\nV1 1 0 10\nR1 1 2 1k\n.include parts.inc\n")
    from minispice import load

    assert load(str(main)).get("R2").value == 1000


def test_missing_include_is_reported(tmp_path):
    main = tmp_path / "main.cir"
    main.write_text("V1 1 0 10\n.include nothere.inc\nR1 1 0 1k\n")
    from minispice import load

    with pytest.raises(NetlistError, match="can't open included file 'nothere.inc'"):
        load(str(main))
