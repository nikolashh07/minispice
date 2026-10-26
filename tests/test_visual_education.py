"""Part E: schematics, results on the schematic, explain mode, homework checker."""

import pathlib
import re

import pytest

from minispice import MiniSpiceError, load, operating_point, parse
from minispice.__main__ import main
from minispice.explain import explain_dc
from minispice.homework import check_answers, diagnose, generate_problem, read_answers
from minispice.schematic import draw_schematic, node_order

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"


# ---- Phases 24-25: schematics -------------------------------------------------------------------

@pytest.mark.parametrize("name", ["divider.cir", "thevenin.cir", "bjt_bias.cir", "inverting_amp.cir",
                                  "transformer.cir", "cmos_inverter.cir", "two_stage_amp.cir", "zener.cir"])
def test_every_kind_of_circuit_draws(tmp_path, name):
    circuit = load(str(EXAMPLES / name))
    svg = tmp_path / "plain.svg"
    png = tmp_path / "annotated.png"
    draw_schematic(circuit, str(svg))
    draw_schematic(circuit, str(png), operating_point(circuit))
    assert svg.read_text(encoding="utf-8").lstrip().startswith(("<?xml", "<svg"))
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_nodes_are_laid_out_from_the_source():
    circuit = parse("R3 3 0 1k\nR2 2 3 1k\nV1 1 0 5\nR1 1 2 1k")
    assert node_order(circuit) == ["1", "2", "3"]


def test_annotations_show_results(tmp_path):
    circuit = load(str(EXAMPLES / "divider.cir"))
    path = tmp_path / "divider.svg"
    draw_schematic(circuit, str(path), operating_point(circuit))
    svg = path.read_text(encoding="utf-8")
    # matplotlib writes each text label as a comment in the SVG.
    assert "2: 5 V" in svg
    assert "25 mW" in svg


def test_overheating_part_is_flagged(tmp_path):
    circuit = parse("V1 1 0 10\nR1 1 2 100 rating=0.25\nR2 2 0 50")
    path = tmp_path / "hot.svg"
    draw_schematic(circuit, str(path), operating_point(circuit))
    svg = path.read_text(encoding="utf-8")
    assert "OVERHEATING" in svg
    assert "#ff0000" in svg.lower()


# ---- Phase 26: explain mode -----------------------------------------------------------------------

def test_walkthrough_reads_like_a_tutor():
    walkthrough, solution = explain_dc(load(str(EXAMPLES / "divider.cir")))
    text = walkthrough.to_text()
    for phrase in ("Node 0 is ground", "KCL at node 2", "(V(2) − V(1)) / 1 kΩ + (V(2) − 0) / 1 kΩ = 0",
                   "V(1) − 0 = 10 V", "single solve", "P = I²R = 25 mW", "energy is conserved ✓"):
        assert phrase in text, phrase
    laws = {step.law for step in walkthrough.steps}
    assert {"Kirchhoff's current law", "Kirchhoff's voltage law", "Ohm's law", "Modified nodal analysis"} <= laws


def test_walkthrough_numbers_check_out():
    walkthrough, _ = explain_dc(load(str(EXAMPLES / "two_sources.cir")))
    kcl = next(s for s in walkthrough.steps if s.title == "KCL at node 2")
    assert kcl.lines[-1].endswith("= 0 A ✓")
    assert set(kcl.parts) == {"R1", "R2", "R3"}


def test_walkthrough_explains_newton_for_nonlinear_circuits():
    walkthrough, _ = explain_dc(load(str(EXAMPLES / "diode.cir")))
    text = walkthrough.to_text()
    assert "Newton's method" in text and "tangent line" in text
    assert "Shockley diode equation" in {s.law for s in walkthrough.steps}


@pytest.mark.parametrize("ext, start", [(".txt", "How MiniSpice"), (".md", "# How MiniSpice"),
                                        (".tex", "\\documentclass"), (".pdf", "%PDF")])
def test_walkthrough_exports(tmp_path, ext, start):
    walkthrough, _ = explain_dc(load(str(EXAMPLES / "thevenin.cir")))
    path = walkthrough.save(str(tmp_path / f"walkthrough{ext}"))
    data = pathlib.Path(path).read_bytes()
    assert data.startswith(start.encode())


def test_walkthrough_for_the_browser():
    data = explain_dc(load(str(EXAMPLES / "divider.cir")))[0].to_dict()
    assert data["steps"][0]["title"] == "Choose the unknowns"
    assert any("R1" in step["parts"] for step in data["steps"])


def test_explain_option(capsys, tmp_path):
    assert main([str(EXAMPLES / "divider.cir"), "--explain"]) == 0
    assert "KCL at node 2" in capsys.readouterr().out
    assert main([str(EXAMPLES / "divider.cir"), "--explain", str(tmp_path / "out.tex")]) == 0
    assert (tmp_path / "out.tex").exists()


def test_schematic_option(capsys, tmp_path):
    assert main([str(EXAMPLES / "thevenin.cir"), "--schematic", str(tmp_path / "s.svg")]) == 0
    assert (tmp_path / "s.svg").exists()


# ---- Phase 27: homework checker -----------------------------------------------------------------

HW = "V1 1 0 12\nR1 1 2 6k\nR2 2 0 3k\nR3 2 0 6k"


def test_right_answers():
    report = check_answers(parse(HW), [("i(R1)", 1.5e-3), ("v(2)", 3.0)])
    assert report.all_correct and report.first_wrong is None


def test_first_wrong_step_is_reported():
    report = check_answers(parse(HW), [("i(R1)", 1.5e-3), ("v(2)", 4.0), ("i(R3)", 0.6e-3)])
    assert report.first_wrong.expr == "v(2)"
    assert report.first_wrong.correct == pytest.approx(3.0)
    text = report.to_text()
    assert "first goes wrong at v(2)" in text and "1 later answer" in text


@pytest.mark.parametrize("given, words", [
    (-1.5e-3, "sign is flipped"),
    (1.5, "1000 too big"),
    (12 / 9e3, "left R3 out"),  # without R3: 12 V / (6k + 3k)
    (12 / 6e3, "treated R2 as a short"),
])
def test_diagnosis_of_common_mistakes(given, words):
    assert words in diagnose(parse(HW), "i(R1)", given, 1.5e-3)


def test_answers_are_read_from_comments():
    text = "* answer: v(2) = 3\nV1 1 0 1\n*answer: i(R1)=1.5mA\n"
    assert read_answers(text) == [("v(2)", 3.0), ("i(R1)", 1.5e-3)]
    with pytest.raises(MiniSpiceError, match="No answers found"):
        check_answers(parse(HW), [])


def test_check_command(capsys):
    code = main(["check", str(EXAMPLES / "homework_example.cir")])
    out = capsys.readouterr().out
    assert code == 3
    assert "left R3 out" in out


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_practice_problems_are_solvable_and_repeatable(level):
    first = generate_problem(seed=42, level=level)
    assert first == generate_problem(seed=42, level=level)
    solution = operating_point(parse(first.netlist))
    for question in first.questions:
        assert solution.measure(question) == solution.measure(question)  # every question has a real answer


def test_practice_command(capsys, monkeypatch):
    problem = generate_problem(seed=3, level=1)
    solution = operating_point(parse(problem.netlist))
    replies = iter([f"{solution.measure(q):.6g}" for q in problem.questions])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))
    assert main(["practice", "--seed", "3"]) == 0
    assert "All 2 answers are right" in capsys.readouterr().out


def test_practice_wrong_answer_shows_solution(capsys, monkeypatch):
    replies = iter(["oops", "1", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))
    assert main(["practice", "--seed", "3"]) == 3
    out = capsys.readouterr().out
    assert "isn't a number" in out and "Here is the full solution" in out
    assert re.search(r"Step \d+: KCL at node 2", out)
