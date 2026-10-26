// The virtual instruments: oscilloscope, Bode plotter, spectrum analyzer and multimeter.
// Each one reads its knobs from the page, asks the engine for data, and draws it.

import { formatEng, parseValue } from "../editor/model.js";
import { CHANNEL_COLORS, SCOPE_STEPS, autoVoltsPerDiv, drawChart, drawScope } from "./plot.js";
import { BoardLink } from "./serial.js";

const $ = (id) => document.getElementById(id);

function readValue(id, fallback) {
  const v = parseValue($(id).value);
  return v === null || !(v > 0) ? fallback : v;
}

function fillSelect(select, options, keep = true) {
  const previous = select.value;
  select.innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
  if (keep && options.some(([value]) => value === previous)) select.value = previous;
}

export class Oscilloscope {
  constructor(app) {
    this.app = app;
    this.data = null;
    this.measured = [[], [], [], []];
    this.board = null;
    $("scope-run").addEventListener("click", () => this.run());
    $("scope-timediv").addEventListener("change", () => this.draw());
    $("scope-connect").addEventListener("click", () => this.toggleBoard());
    $("scope-clear-measured").addEventListener("click", () => { this.measured = [[], [], [], []]; this.draw(); });
    if (!BoardLink.supported()) $("scope-connect").title = "Web Serial needs Chrome or Edge on a computer";
    fillSelect($("scope-timediv"), [["auto", "auto"], ...SCOPE_STEPS.map((s) => [String(s), formatEng(s, "s") + "/div"])]);
    new ResizeObserver(() => this.draw()).observe($("scope-canvas"));
  }

  settings() {
    const stop = readValue("scope-stop", 5e-3);
    const step = readValue("scope-step", stop / 500);
    return { stop, step };
  }

  async run() {
    const probes = this.app.probes;
    if (!probes.length) {
      this.app.status("Add a probe first: pick the probe tool and click a wire.", true);
      return;
    }
    const { stop, step } = this.settings();
    this.app.status("Running transient analysis…");
    const result = await this.app.engine.transient(this.app.netlist(), step, stop, probes.map((p) => `v(${p})`));
    if (!result.ok) {
      this.app.status(result.error, true);
      return;
    }
    this.data = result;
    this.app.status(`Transient done: ${result.times.length} points to ${formatEng(stop, "s")}.`);
    this.draw();
  }

  draw() {
    const canvas = $("scope-canvas");
    if (!canvas.clientWidth) return;
    const { stop } = this.settings();
    const choice = $("scope-timediv").value;
    const timePerDiv = choice === "auto" ? stop / 10 : Number(choice);
    const channels = [];
    this.app.probes.forEach((probe, k) => {
      const series = this.data && this.data.series[`v(${probe})`];
      const measured = this.measured[k];
      const values = series || measured.map((s) => s.v);
      const vdiv = autoVoltsPerDiv(values.length ? values.concat(measured.map((s) => s.v)) : [1]);
      if (series) channels.push({ label: `CH${k + 1} v(${probe})`, times: this.data.times, values: series, color: CHANNEL_COLORS[k], voltsPerDiv: vdiv });
      if (measured.length) {
        // Show the most recent screenful of board samples, scrolling like a real scope.
        const tEnd = measured[measured.length - 1].t;
        const shown = measured.filter((s) => s.t >= tEnd - timePerDiv * 10);
        const t0 = Math.max(0, tEnd - timePerDiv * 10);
        channels.push({ label: `CH${k + 1} measured`, times: shown.map((s) => s.t - t0), values: shown.map((s) => s.v), color: CHANNEL_COLORS[k], voltsPerDiv: vdiv, dashed: true });
      }
    });
    drawScope(canvas, { timePerDiv, channels });
  }

  async toggleBoard() {
    if (this.board) {
      await this.board.disconnect();
      this.board = null;
      $("scope-connect").textContent = "Connect board";
      return;
    }
    this.board = new BoardLink({
      vref: readValue("scope-vref", 5),
      bits: Number($("scope-bits").value) || 10,
      onStatus: (text) => this.app.status(text),
      onSample: (sample) => {
        // Analog input k overlays scope channel k+1 (A0 on CH1, A1 on CH2, ...).
        sample.volts.slice(0, 4).forEach((v, k) => {
          this.measured[k].push({ t: sample.t, v });
          if (this.measured[k].length > 5000) this.measured[k].shift();
        });
        if (!this._pending) {
          this._pending = true;
          requestAnimationFrame(() => { this._pending = false; this.draw(); });
        }
      },
    });
    try {
      await this.board.connect();
      $("scope-connect").textContent = "Disconnect board";
    } catch (error) {
      this.board = null;
      this.app.status(String(error.message || error), true);
    }
  }
}

export class BodePlotter {
  constructor(app) {
    this.app = app;
    this.data = null;
    $("bode-run").addEventListener("click", () => this.run());
    new ResizeObserver(() => this.draw()).observe($("bode-mag"));
  }

  refresh(info) {
    fillSelect($("bode-source"), info.sources.map((s) => [s, s]));
    fillSelect($("bode-output"), info.nets.map((n) => [n, `node ${n}`]));
  }

  async run() {
    const source = $("bode-source").value;
    const output = $("bode-output").value;
    if (!source || !output) {
      this.app.status("The Bode plotter needs a voltage source to drive and a node to measure.", true);
      return;
    }
    const f1 = readValue("bode-fstart", 1);
    const f2 = readValue("bode-fstop", 1e6);
    this.app.status("Running AC sweep…");
    const result = await this.app.engine.ac(this.app.netlist(), source, f1, f2, 20, [`v(${output})`]);
    if (!result.ok) {
      this.app.status(result.error, true);
      return;
    }
    this.data = { ...result, probe: `v(${output})` };
    const mag = result.magnitude_db[this.data.probe];
    const target = mag[0] - 3.0103;
    const k = mag.findIndex((m) => m <= target);
    const low = Math.abs(mag[0]) < 0.005 ? 0 : mag[0]; // avoid printing -0.00
    let text = `Gain at ${formatEng(result.freqs[0], "Hz")}: ${low.toFixed(2)} dB.`;
    if (k > 0) {
      // Interpolate on a log-frequency axis between the two sweep points either side of -3 dB.
      const [f0, f1] = [Math.log10(result.freqs[k - 1]), Math.log10(result.freqs[k])];
      const corner = Math.pow(10, f0 + ((target - mag[k - 1]) * (f1 - f0)) / (mag[k] - mag[k - 1]));
      text += ` 3 dB down at ${formatEng(corner, "Hz")}.`;
    }
    $("bode-readout").textContent = text;
    this.app.status("AC sweep done.");
    this.draw();
  }

  draw() {
    if (!this.data || !$("bode-mag").clientWidth) return;
    const { freqs, magnitude_db: mag, phase, probe } = this.data;
    drawChart($("bode-mag"), { series: [{ x: freqs, y: mag[probe], color: CHANNEL_COLORS[1], label: `|${probe}|` }], logX: true, xUnit: "Hz", yUnit: "dB", yLabel: "magnitude" });
    drawChart($("bode-phase"), { series: [{ x: freqs, y: phase[probe], color: CHANNEL_COLORS[2], label: "phase" }], logX: true, xUnit: "Hz", yUnit: "°", yLabel: "phase" });
  }
}

export class SpectrumAnalyzer {
  constructor(app, scope) {
    this.app = app;
    this.scope = scope;
    this.data = null;
    $("spectrum-run").addEventListener("click", () => this.run());
    $("spectrum-log").addEventListener("change", () => this.draw());
    new ResizeObserver(() => this.draw()).observe($("spectrum-canvas"));
  }

  refresh(info) {
    fillSelect($("spectrum-probe"), info.nets.map((n) => [n, `node ${n}`]));
  }

  async run() {
    const node = $("spectrum-probe").value;
    const { stop, step } = this.scope.settings();
    this.app.status("Running transient analysis for the spectrum…");
    const result = await this.app.engine.spectrum(this.app.netlist(), step, stop, `v(${node})`);
    if (!result.ok) {
      this.app.status(result.error, true);
      return;
    }
    this.data = result;
    const peak = result.amplitudes.reduce((best, a, k) => (k > 0 && a > result.amplitudes[best] ? k : best), 1);
    $("spectrum-readout").textContent = `Strongest tone: ${formatEng(result.freqs[peak], "Hz")} at ${formatEng(result.amplitudes[peak], "V")} peak. ` +
      `Resolution ${formatEng(1 / stop, "Hz")} (a longer run gives finer resolution).`;
    this.app.status("Spectrum done.");
    this.draw();
  }

  draw() {
    if (!this.data || !$("spectrum-canvas").clientWidth) return;
    const log = $("spectrum-log").checked;
    const x = this.data.freqs.slice(1);
    const y = this.data.amplitudes.slice(1).map((a) => (log ? 20 * Math.log10(Math.max(a, 1e-12)) : a));
    drawChart($("spectrum-canvas"), { series: [{ x, y, color: CHANNEL_COLORS[0], label: "amplitude" }], logX: true, xUnit: "Hz", yUnit: log ? "dB" : "V", yLabel: log ? "dBV" : "amplitude" });
  }
}

export class Multimeter {
  constructor(app) {
    this.app = app;
    this.last = null;
    for (const id of ["meter-mode", "meter-plus", "meter-com", "meter-part"]) $(id).addEventListener("change", () => this.update(this.last));
  }

  refresh(info) {
    const nets = [["0", "ground (0)"], ...info.nets.map((n) => [n, `node ${n}`])];
    fillSelect($("meter-plus"), nets);
    fillSelect($("meter-com"), nets);
    fillSelect($("meter-part"), info.parts.map((p) => [p, p]));
    const voltage = $("meter-mode").value === "V";
    $("meter-voltage-leads").hidden = !voltage;
    $("meter-part-lead").hidden = voltage;
  }

  update(result) {
    this.last = result;
    const mode = $("meter-mode").value;
    $("meter-voltage-leads").hidden = mode !== "V";
    $("meter-part-lead").hidden = mode === "V";
    const display = $("meter-display");
    if (!result || !result.ok) {
      display.textContent = "----";
      return;
    }
    if (mode === "V") {
      const v = (n) => (n === "0" ? 0 : result.nodes[n]);
      const plus = v($("meter-plus").value);
      const com = v($("meter-com").value);
      display.textContent = plus === undefined || com === undefined ? "----" : formatEng(plus - com, "V");
      return;
    }
    const part = result.parts.find((p) => p.name === $("meter-part").value);
    if (!part) {
      display.textContent = "----";
      return;
    }
    display.textContent = mode === "A" ? formatEng(part.currents[0], "A") : formatEng(part.power, "W");
  }
}
