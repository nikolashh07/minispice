"""Run the web app's JavaScript unit tests without Node.js, using the V8 engine from `mini-racer`.

    pip install mini-racer          (a development tool only; the app itself doesn't need it)
    python tools/run_js_tests.py

Each test file is run together with the module it tests. ES module syntax (import/export) is
stripped, because the tests run as one plain script.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "web"
SUITES = {
    "tests/model_test.js": ["editor/model.js"],
    "tests/serial_test.js": ["scope/serial.js"],
    "tests/breadboard_test.js": ["editor/model.js", "breadboard/layout.js"],
}
SYNTAX_ONLY = ["editor/editor.js", "scope/plot.js", "scope/instruments.js", "explain.js", "examples.js",
               "app.js", "engine-bridge.js", "engine-worker.js", "breadboard/breadboard.js"]


def as_script(source):
    source = re.sub(r"^\s*import\s.*?;\s*$", "", source, flags=re.M)
    # import.meta only exists inside a module; a stand-in keeps the syntax check honest.
    source = source.replace("import.meta", "({url: ''})")
    return re.sub(r"^export\s+(default\s+)?", "", source, flags=re.M)


def main():
    try:
        from py_mini_racer import MiniRacer
    except ImportError:
        print("Install the V8 engine first: pip install mini-racer")
        return 2
    failures = 0
    for test_file, modules in SUITES.items():
        ctx = MiniRacer()
        code = "".join(as_script((ROOT / m).read_text(encoding="utf-8")) + "\n" for m in modules)
        code += as_script((ROOT / test_file).read_text(encoding="utf-8"))
        ctx.eval(code)
        for name in ctx.eval("Object.keys(tests)"):
            try:
                ctx.eval(f"tests[{name!r}]()")
                print(f"  ok    {test_file}: {name}")
            except Exception as error:  # the JS error message is the useful part
                failures += 1
                print(f"  FAIL  {test_file}: {name}: {error}")
    # Files that need a browser can at least be checked for syntax errors.
    for path in SYNTAX_ONLY:
        file = ROOT / path
        if not file.exists():
            continue
        try:
            MiniRacer().eval("new Function(" + repr(as_script(file.read_text(encoding="utf-8"))) + ")")
            print(f"  ok    {path}: syntax")
        except Exception as error:
            failures += 1
            print(f"  FAIL  {path}: syntax: {error}")
    failures += check_examples(MiniRacer)
    print("all JavaScript tests passed" if failures == 0 else f"{failures} JavaScript test(s) failed")
    return 1 if failures else 0


def check_examples(MiniRacer):
    """Each starter design must turn into a netlist the Python engine can solve, with the answer
    its comment promises. This catches a wire drawn one grid square off."""
    sys.path.insert(0, str(ROOT.parent))
    from minispice import operating_point, parse

    expected = {"Voltage divider": ("v(2)", 5.0), "LED and resistor": ("i(R1)", 9.7e-3), "Inverting amplifier": None,
                "RC low-pass filter": ("v(2)", 0.0), "CMOS inverter": ("v(2)", 5.0)}
    ctx = MiniRacer()
    ctx.eval(as_script((ROOT / "editor/model.js").read_text(encoding="utf-8")) + as_script((ROOT / "examples.js").read_text(encoding="utf-8")))
    failures = 0
    for name in ctx.eval("Object.keys(EXAMPLES)"):
        netlist = ctx.eval(f"toNetlist(fromNetlist(EXAMPLES[{name!r}]))")
        try:
            solution = operating_point(parse(netlist))
            check = expected.get(name)
            if check:
                probe, value = check
                got = solution.measure(probe)
                assert abs(got - value) <= 0.02 * max(abs(value), 1e-3), f"{probe} = {got}, expected {value}"
            print(f"  ok    examples.js: {name}")
        except Exception as error:
            failures += 1
            print(f"  FAIL  examples.js: {name}: {error}\n{netlist}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
