// Wires the page together: the editor, the Python engine, the instruments, and explain mode.

import { Editor, escapeHtml, symbolSvg } from "./editor/editor.js";
import { PART_TYPES, buildNets, formatEng, fromNetlist, mainValue, spiceValue } from "./editor/model.js";
import { Engine } from "./engine-bridge.js";
import { EXAMPLES } from "./examples.js";
import { ExplainPanel } from "./explain.js";
import { BodePlotter, Multimeter, Oscilloscope, SpectrumAnalyzer } from "./scope/instruments.js";

const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "minispice.design";
const PALETTE = ["R", "C", "L", "V", "I", "D", "LED", "S", "NPN", "PNP", "NMOS", "PMOS", "OPAMP", "GND"];

class App {
  constructor() {
    this.probes = [];
    this.lastResult = null;
    this.solveTimer = null;
    this.solving = false;
    this.engine = new Engine((text) => this.status(text));
    this.editor = new Editor($("schematic"), {
      onChange: (netlist) => this.changed(netlist),
      onSelect: (part) => this.inspect(part),
      onProbe: (net) => this.toggleProbe(net),
    });
    this.scope = new Oscilloscope(this);
    this.bode = new BodePlotter(this);
    this.spectrum = new SpectrumAnalyzer(this, this.scope);
    this.meter = new Multimeter(this);
    this.explain = new ExplainPanel(this);
    this.buildPalette();
    this.bindToolbar();
    this.bindTabs();
    this.bindNetlistTab();
    this.restore();
    this.engine.ready.then(() => this.solveSoon(0)).catch(() => {});
  }

  // ---- status and netlist ----------------------------------------------------------------------
  status(text, isError = false) {
    const bar = $("status");
    bar.textContent = text;
    bar.classList.toggle("error", isError);
  }

  netlist() {
    return this.editor.netlist($("design-title").value || "MiniSpice editor design");
  }

  info() {
    const nets = new Set();
    const nodes = buildNets(this.editor.design);
    for (const pins of nodes.pinNets.values()) pins.forEach((n) => n !== "0" && nets.add(n));
    const parts = this.editor.design.parts.filter((p) => p.type !== "GND");
    return {
      nets: [...nets].sort((a, b) => Number(a) - Number(b)),
      sources: parts.filter((p) => p.type === "V").map((p) => p.name),
      parts: parts.map((p) => p.name),
    };
  }

  changed(netlist) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ title: $("design-title").value, design: this.editor.design }));
    } catch (error) {
      // Private browsing can block storage; the editor still works, it just won't remember.
    }
    if (!$("netlist-text").dataset.edited) $("netlist-text").value = netlist;
    const info = this.info();
    this.probes = this.probes.filter((p) => info.nets.includes(p));
    this.editor.setProbes(this.probes);
    this.bode.refresh(info);
    this.spectrum.refresh(info);
    this.meter.refresh(info);
    this.explain.reset();
    if ($("live").checked) this.solveSoon();
  }

  // Solve a moment after the last change, so dragging a slider doesn't queue up hundreds of solves.
  solveSoon(delay = 120) {
    clearTimeout(this.solveTimer);
    this.solveTimer = setTimeout(() => this.solveNow(), delay);
  }

  async solveNow() {
    if (this.solving) {
      this.solveSoon();
      return;
    }
    const hasParts = this.editor.design.parts.some((p) => p.type !== "GND");
    if (!hasParts) {
      this.editor.setResults(null);
      this.status("Pick a part from the palette and click on the grid to place it.");
      return;
    }
    this.solving = true;
    const result = await this.engine.solve(this.netlist());
    this.solving = false;
    this.lastResult = result;
    this.editor.setResults(result);
    this.meter.update(result);
    this.updateReadout(this.selectedPart());
    if (result.ok) {
      const warnings = result.warnings.filter((w) => !w.includes("is not used by MiniSpice"));
      this.status(warnings.length ? warnings[0] : `Solved: sources deliver ${formatEng(result.power.delivered, "W")}.`, warnings.length > 0);
    } else {
      this.status(result.error, true);
    }
  }

  selectedPart() {
    const s = this.editor.selected;
    return s && s.kind === "part" ? this.editor.part(s.id) : null;
  }

  // ---- palette and toolbar ---------------------------------------------------------------------
  buildPalette() {
    const palette = $("palette");
    for (const type of PALETTE) {
      const button = document.createElement("button");
      button.className = "part-button";
      button.title = PART_TYPES[type].label;
      button.innerHTML = `${symbolSvg(type, 36)}<span>${PART_TYPES[type].label}</span>`;
      button.addEventListener("click", () => this.setMode("place", type));
      button.dataset.type = type;
      palette.appendChild(button);
    }
  }

  setMode(mode, type = null) {
    this.editor.setMode(mode, type);
    document.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    document.querySelectorAll(".part-button").forEach((b) => b.classList.toggle("active", mode === "place" && b.dataset.type === type));
    const hints = {
      select: "Drag parts to move them. R rotates, Delete removes, Ctrl+Z undoes.",
      wire: "Click to start a wire, click again to bend or finish it. Double-click or Esc to stop.",
      probe: "Click a wire or pin to add or remove an oscilloscope probe (up to 4).",
      place: `Click the grid to place a ${PART_TYPES[type] ? PART_TYPES[type].label.toLowerCase() : "part"}. Right-click or Esc when done.`,
    };
    this.status(hints[mode]);
  }

  bindToolbar() {
    document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => this.setMode(b.dataset.mode)));
    $("rotate").addEventListener("click", () => this.editor.rotateSelected());
    $("delete").addEventListener("click", () => this.editor.deleteSelected());
    $("undo").addEventListener("click", () => this.editor.undo());
    $("redo").addEventListener("click", () => this.editor.redo());
    $("new").addEventListener("click", () => {
      if (confirm("Start a new, empty design? (Undo can bring the old one back.)")) this.editor.clear();
    });
    $("save").addEventListener("click", () => this.download(`${this.fileStem()}.minispice.json`, JSON.stringify({ title: $("design-title").value, design: this.editor.design }, null, 1)));
    $("export").addEventListener("click", () => this.download(`${this.fileStem()}.cir`, this.netlist()));
    $("open").addEventListener("click", () => $("open-file").click());
    $("open-file").addEventListener("change", (event) => this.openFile(event.target.files[0]));
    $("live").addEventListener("change", () => ($("live").checked ? this.solveSoon(0) : this.editor.setResults(null)));
    $("animate").addEventListener("change", () => { this.editor.animate = $("animate").checked; });
    $("design-title").addEventListener("change", () => this.changed(this.netlist()));
    const select = $("examples");
    select.innerHTML = `<option value="">Examples…</option>` + Object.keys(EXAMPLES).map((name) => `<option>${name}</option>`).join("");
    select.addEventListener("change", () => {
      if (select.value) this.loadNetlist(EXAMPLES[select.value], select.value);
      select.value = "";
    });
  }

  fileStem() {
    return ($("design-title").value || "circuit").replace(/[^\w-]+/g, "_").slice(0, 40) || "circuit";
  }

  download(name, text) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  async openFile(file) {
    if (!file) return;
    const text = await file.text();
    $("open-file").value = "";
    try {
      if (file.name.endsWith(".json")) {
        const saved = JSON.parse(text);
        $("design-title").value = saved.title || file.name;
        this.editor.load(saved.design);
      } else {
        this.loadNetlist(text, file.name.replace(/\.\w+$/, ""));
      }
    } catch (error) {
      this.status(`Couldn't open ${file.name}: ${error.message}`, true);
    }
  }

  loadNetlist(text, title) {
    try {
      const design = fromNetlist(text);
      const firstComment = text.split(/\r?\n/).find((l) => l.startsWith("*") && !l.includes("@"));
      $("design-title").value = title || (firstComment ? firstComment.slice(1).trim() : "Imported circuit");
      this.probes = [];
      this.editor.load(design);
    } catch (error) {
      this.status(error.message, true);
    }
  }

  restore() {
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    } catch (error) {
      saved = null;
    }
    if (saved && saved.design && saved.design.parts.length) {
      $("design-title").value = saved.title || "";
      this.editor.load(saved.design, false);
    } else {
      this.loadNetlist(EXAMPLES["Voltage divider"], "Voltage divider");
    }
  }

  toggleProbe(net) {
    if (net === "0") {
      this.status("Ground is the scope's reference (0 V); probe another node.", true);
      return;
    }
    if (this.probes.includes(net)) this.probes = this.probes.filter((p) => p !== net);
    else if (this.probes.length < 4) this.probes.push(net);
    else {
      this.status("The scope has four channels. Remove a probe first.", true);
      return;
    }
    this.editor.setProbes(this.probes);
    this.status(`Probes on: ${this.probes.map((p, k) => `CH${k + 1} = node ${p}`).join(", ") || "none"}`);
  }

  // ---- inspector -------------------------------------------------------------------------------
  inspect(part) {
    const box = $("inspector-body");
    if (!part || part.type === "GND") {
      box.innerHTML = `<p class="hint">Select a part to edit it. Hover over anything to see its voltage, current and power.</p>`;
      return;
    }
    const info = PART_TYPES[part.type];
    const numeric = info.numeric && mainValue(part.value) !== null;
    let html = `<label>Name <input id="ins-name" value="${escapeHtml(part.name)}"></label>
      <label>${numeric ? "Value" : info.letter === "V" || info.letter === "I" ? "Value or waveform" : "Model / options"}
        <input id="ins-value" value="${escapeHtml(part.value)}"></label>`;
    if (numeric) {
      html += `<label>Adjust live <input id="ins-slider" type="range" min="-1" max="1" step="0.01" value="0"></label>
        <p class="hint">The slider spans a tenth to ten times <span id="ins-base">${escapeHtml(part.value)}</span>.</p>`;
    }
    html += `<div id="ins-readout"></div>`;
    box.innerHTML = html;
    this.updateReadout(part);
    $("ins-name").addEventListener("change", (e) => this.editor.updatePart(part.id, { name: e.target.value.trim() || part.name }));
    $("ins-value").addEventListener("change", (e) => this.editor.updatePart(part.id, { value: e.target.value.trim() }));
    if (numeric) {
      // A logarithmic slider: equal steps multiply the value, so 100 Ω and 100 kΩ both feel natural.
      // Only the number at the start changes; options after it (like rating=0.25) are kept.
      const base = mainValue(part.value);
      const options = part.value.trim().split(/\s+/).slice(1);
      const slider = $("ins-slider");
      let before = null;
      slider.addEventListener("input", () => {
        if (before === null) before = this.editor.snapshot();
        part.value = [spiceValue(base * Math.pow(10, Number(slider.value))), ...options].join(" ");
        $("ins-value").value = part.value;
        this.editor.render();
        this.solveSoon(30);
      });
      // Letting go of the slider makes the whole drag one undoable edit.
      slider.addEventListener("change", () => {
        if (before !== null) this.editor.commit(before);
        before = null;
      });
    }
  }

  // Live results for the selected part. Kept separate from inspect() so a solve that finishes
  // while a slider is being dragged doesn't rebuild the slider out from under the mouse.
  updateReadout(part) {
    const box = $("ins-readout");
    if (!box || !part) return;
    const result = this.lastResult && this.lastResult.ok ? this.lastResult.parts.find((p) => p.name === part.name) : null;
    if (!result) {
      box.innerHTML = "";
      return;
    }
    let html = `<table class="readout">
      <tr><th>Current</th><td>${formatEng(result.currents[0], "A")}</td></tr>
      <tr><th>Voltage</th><td>${formatEng(result.voltage, "V")}</td></tr>
      <tr><th>Power</th><td>${formatEng(result.power, "W")}</td></tr>
      ${result.region ? `<tr><th>Region</th><td>${escapeHtml(result.region)}</td></tr>` : ""}
    </table>`;
    if (result.rating && result.power > result.rating) html += `<p class="danger">Overheating: rated ${formatEng(result.rating, "W")}.</p>`;
    box.innerHTML = html;
  }

  // ---- tabs --------------------------------------------------------------------------------------
  bindTabs() {
    document.querySelectorAll("#tabs button").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll("#tabs button").forEach((t) => t.classList.toggle("active", t === tab));
        document.querySelectorAll(".tab-page").forEach((page) => { page.hidden = page.id !== tab.dataset.tab; });
        if (tab.dataset.tab !== "tab-explain") this.editor.setHighlight([]);
        this.scope.draw();
        this.bode.draw();
        this.spectrum.draw();
      });
    });
  }

  bindNetlistTab() {
    const text = $("netlist-text");
    text.addEventListener("input", () => { text.dataset.edited = "1"; });
    $("netlist-solve").addEventListener("click", async () => {
      // Phase 28's simple page: paste any netlist, click Solve, see the results.
      const result = await this.engine.solve(text.value);
      $("netlist-results").innerHTML = result.ok ? resultsTable(result) : `<p class="danger">${escapeHtml(result.error)}</p>`;
    });
    $("netlist-load").addEventListener("click", () => {
      delete text.dataset.edited;
      this.loadNetlist(text.value);
    });
    $("netlist-reset").addEventListener("click", () => {
      delete text.dataset.edited;
      text.value = this.netlist();
    });
  }
}

function resultsTable(result) {
  const nodes = Object.entries(result.nodes).map(([n, v]) => `<tr><td>${escapeHtml(n)}</td><td>${formatEng(v, "V")}</td></tr>`).join("");
  const parts = result.parts.map((p) => `<tr><td>${escapeHtml(p.name)}</td><td>${escapeHtml(p.kind)}${p.region ? ` (${escapeHtml(p.region)})` : ""}</td>
    <td>${formatEng(p.voltage, "V")}</td><td>${formatEng(p.currents[0], "A")}</td><td>${formatEng(p.power, "W")}</td></tr>`).join("");
  return `<table class="results"><tr><th>Node</th><th>Voltage</th></tr>${nodes}</table>
    <table class="results"><tr><th>Part</th><th>Type</th><th>Voltage</th><th>Current</th><th>Power</th></tr>${parts}</table>
    <p>Sources deliver ${formatEng(result.power.delivered, "W")}; the power balance ${result.power.balanced ? "checks out ✓" : "does NOT check out"}.</p>`;
}

window.app = new App();
