"""Checks on the browser app that don't need a browser (Part F)."""

import json
import pathlib
import re
import subprocess
import sys

import pytest

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"
IMPORT = re.compile(r'^import\s+(?:\{([^}]*)\}|\*\s+as\s+\w+)\s+from\s+"([^"]+)";', re.M)
EXPORT = re.compile(r"^export\s+(?:async\s+)?(?:function|class|const|let)\s+(\w+)", re.M)


def js_files():
    return sorted(p for p in WEB.rglob("*.js") if "tests" not in p.parts and "engine" not in p.parts[-2:-1])


@pytest.mark.parametrize("path", js_files(), ids=lambda p: p.relative_to(WEB).as_posix())
def test_imports_resolve(path):
    """Every relative import names a real file, and every imported name is exported there."""
    source = path.read_text(encoding="utf-8")
    for names, target in IMPORT.findall(source):
        if not target.startswith("."):
            continue  # CDN packages (three.js) are mapped in the page's import map
        module = (path.parent / target).resolve()
        assert module.exists(), f"{path.name} imports missing {target}"
        exported = set(EXPORT.findall(module.read_text(encoding="utf-8")))
        for name in (n.strip() for n in names.split(",") if n.strip()):
            assert name in exported, f"{path.name} imports {name} from {target}, which doesn't export it"


def test_pages_reference_existing_files():
    for page in (WEB / "index.html", WEB / "breadboard" / "index.html"):
        html = page.read_text(encoding="utf-8")
        for ref in re.findall(r'(?:src|href)="([^"#:]+)"', html):
            assert (page.parent / ref).exists(), f"{page.name} links to missing {ref}"


def test_element_ids_used_by_scripts_exist():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    for path in [WEB / "app.js", WEB / "explain.js", WEB / "scope" / "instruments.js"]:
        for wanted in re.findall(r'\$\("([^"]+)"\)', path.read_text(encoding="utf-8")):
            if wanted.startswith("ins-"):
                continue  # inspector fields are created on the fly
            assert wanted in ids, f"{path.name} looks for #{wanted}, which index.html doesn't have"


def test_engine_bundle_runs_on_its_own(tmp_path):
    """Unpack the bundle like the browser's worker does and use it from a clean Python."""
    sys.path.insert(0, str(WEB))
    import build_engine

    bundle_path, count = build_engine.build(tmp_path / "minispice.json")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert count == len(bundle["files"]) and "minispice/webapi.py" in bundle["files"]
    root = tmp_path / "fs"
    for name, source in bundle["files"].items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    script = (
        "import sys, json; sys.path.insert(0, sys.argv[1]);"
        "import minispice.webapi as api;"
        "print(json.loads(api.call('solve', json.dumps(['V1 1 0 10\\nR1 1 2 1k\\nR2 2 0 1k'])))['nodes']['2']);"
        "print('matplotlib' in sys.modules, 'scipy' in sys.modules)"
    )
    # -I: isolated mode, so only the unpacked bundle (plus installed numpy) can be imported.
    out = subprocess.run([sys.executable, "-I", "-c", script, str(root)], capture_output=True, text=True, check=True).stdout.split()
    assert out == ["5.0", "False", "False"]
