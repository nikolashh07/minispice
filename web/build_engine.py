"""Bundle the Python engine for the browser: python web/build_engine.py

Writes web/engine/minispice.json, holding the source of every file in the minispice package.
The page's Web Worker writes those files into Pyodide's virtual file system and imports them, so
the browser runs exactly the same engine as the command line.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "minispice"
OUT = pathlib.Path(__file__).resolve().parent / "engine" / "minispice.json"


def build(out=OUT):
    sys.path.insert(0, str(ROOT))
    from minispice import __version__

    files = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        files[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"version": __version__, "files": files}), encoding="utf-8")
    return out, len(files)


if __name__ == "__main__":
    path, count = build()
    print(f"Bundled {count} files into {path}")
    print("Serve the web folder to try it: python -m http.server --directory web  then open http://localhost:8000")
