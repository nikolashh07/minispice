// The page's handle on the Python engine. Each call posts a message to the worker and returns a
// promise for the JSON result, so the rest of the app just writes `await engine.solve(netlist)`.

export class Engine {
  constructor(onStatus = () => {}) {
    this.worker = new Worker(new URL("./engine-worker.js", import.meta.url));
    this.pending = new Map();
    this.nextId = 1;
    this.ready = new Promise((resolve, reject) => {
      this.worker.onmessage = (event) => {
        const data = event.data;
        if (data.status) onStatus(data.status);
        if (data.ready) {
          onStatus(`Engine ready (MiniSpice ${data.version})`);
          resolve();
        }
        if (data.failed) {
          onStatus("The Python engine failed to load: " + data.failed);
          reject(new Error(data.failed));
        }
        if (data.id && this.pending.has(data.id)) {
          this.pending.get(data.id)(data.result);
          this.pending.delete(data.id);
        }
      };
    });
  }

  call(fn, ...args) {
    const id = this.nextId++;
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      this.worker.postMessage({ id, fn, args });
    });
  }

  solve(netlist) { return this.call("solve", netlist); }
  transient(netlist, tStep, tStop, probes) { return this.call("transient", netlist, tStep, tStop, probes); }
  ac(netlist, source, fStart, fStop, perDecade, probes) { return this.call("ac", netlist, source, fStart, fStop, perDecade, probes); }
  spectrum(netlist, tStep, tStop, probe) { return this.call("spectrum", netlist, tStep, tStop, probe); }
  explain(netlist) { return this.call("explain", netlist); }
  check(netlist) { return this.call("check", netlist); }
}
