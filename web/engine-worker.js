// Runs the Python engine in a background thread (a Web Worker), so a long simulation never
// freezes the page. The page sends {id, fn, args}; the worker calls minispice.webapi.call(fn, args)
// inside Pyodide and posts back {id, result}. Only JSON text crosses between the two languages.

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
importScripts(PYODIDE_URL + "pyodide.js");

let api = null;

async function start() {
  postMessage({ status: "Downloading Python (about 10 MB, only the first time)…" });
  const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
  postMessage({ status: "Loading numpy…" });
  await pyodide.loadPackage(["numpy"]);
  postMessage({ status: "Loading the MiniSpice engine…" });
  // engine/minispice.json holds every .py file of the package (made by web/build_engine.py).
  const bundle = await (await fetch("engine/minispice.json")).json();
  for (const [path, source] of Object.entries(bundle.files)) {
    const folder = path.split("/").slice(0, -1).join("/");
    pyodide.FS.mkdirTree("/home/pyodide/" + folder);
    pyodide.FS.writeFile("/home/pyodide/" + path, source);
  }
  pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  api = pyodide.pyimport("minispice.webapi");
  postMessage({ ready: true, version: bundle.version });
}

const started = start().catch((error) => postMessage({ failed: String(error) }));

onmessage = async (event) => {
  const { id, fn, args } = event.data;
  await started;
  if (!api) {
    postMessage({ id, result: { ok: false, error: "The Python engine failed to load." } });
    return;
  }
  try {
    const text = api.call(fn, JSON.stringify(args));
    postMessage({ id, result: JSON.parse(text) });
  } catch (error) {
    // A Python exception that isn't a MiniSpice error: report it instead of hanging the request.
    postMessage({ id, result: { ok: false, error: "Engine crash: " + String(error).split("\n").slice(-2).join(" ") } });
  }
};
