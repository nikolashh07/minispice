// The drag-and-drop schematic editor: draws a design as SVG and turns mouse and keyboard input
// into edits. All the electrical logic (nodes, netlists, wire currents) lives in model.js.

import { GRID, PART_TYPES, buildNets, formatEng, nextName, pinPositions, toNetlist, wireCurrents } from "./model.js";

const G = GRID;

// Part symbols at rotation 0, in pixels, centered on the part's origin. Pins sit at multiples of G.
const SYMBOLS = {
  R: `<path d="M-40,0H-20L-16,-7L-8,7L0,-7L8,7L16,-7L20,0H40"/>`,
  C: `<path d="M-40,0H-4M4,0H40M-4,-13V13M4,-13V13"/>`,
  L: `<path d="M-40,0H-20a5,5 0 0 1 10,0a5,5 0 0 1 10,0a5,5 0 0 1 10,0a5,5 0 0 1 10,0H40"/>`,
  V: `<path d="M0,-40V-14M0,14V40"/><circle r="14"/><path d="M-4,-6H4M0,-10V-2M-4,7H4"/>`,
  I: `<path d="M0,-40V-14M0,14V40"/><circle r="14"/><path d="M0,9V-8M-4,-3L0,-9L4,-3"/>`,
  D: `<path d="M-40,0H-9M9,0H40M9,-9V9"/><path class="fill" d="M-9,-9V9L9,0Z"/>`,
  LED: `<path d="M-40,0H-9M9,0H40M9,-9V9"/><path class="fill" d="M-9,-9V9L9,0Z"/><path d="M0,-12L6,-20M6,-20L2,-19M6,-20L5,-16M7,-9L13,-17M13,-17L9,-16M13,-17L12,-13"/>`,
  NPN: `<path d="M-40,0H-6M-6,-14V14M-6,-6L20,-22V-40M-6,6L20,22V40"/><path class="fill" d="M20,22L10,21L15,13Z"/>`,
  PNP: `<path d="M-40,0H-6M-6,-14V14M-6,6L20,22V40M-6,-6L20,-22V-40"/><path class="fill" d="M-6,-6L4,-7L-1,-15Z"/>`,
  NMOS: `<path d="M-40,0H-10M-10,-16V16M-4,-18V-6M-4,-4V4M-4,6V18M-4,-12H20V-40M-4,12H20V40M-4,0H20V12"/><path class="fill" d="M-4,0L4,-4V4Z"/>`,
  PMOS: `<path d="M-40,0H-14M-10,-16V16M-4,-18V-6M-4,-4V4M-4,6V18M-4,12H20V40M-4,-12H20V-40M-4,0H20V-12"/><circle cx="-12" r="2.5"/><path class="fill" d="M20,0L12,-4V4Z"/>`,
  OPAMP: `<path d="M-40,20H-24M-40,-20H-24M28,0H40"/><path d="M-24,-32V32L28,0Z"/><path d="M-20,-20H-12M-20,20H-12M-16,16V24"/>`,
  S: `<path d="M-40,0H-20M20,0H40M-20,0L16,-14"/><circle cx="-20" r="2.5"/><circle cx="20" r="2.5"/>`,
  GND: `<path d="M0,0V10M-12,10H12M-7,15H7M-2,20H2"/>`,
};

export class Editor {
  constructor(svg, { onChange = () => {}, onSelect = () => {}, onProbe = () => {} } = {}) {
    this.svg = svg;
    this.onChange = onChange;
    this.onSelect = onSelect;
    this.onProbe = onProbe;
    this.design = { parts: [], wires: [] };
    this.nextId = 1;
    this.mode = "select";
    this.placeType = null;
    this.selected = null; // {kind: "part"|"wire", id}
    this.undoStack = [];
    this.redoStack = [];
    this.results = null;
    this.highlight = new Set();
    this.probes = [];
    this.animate = true;
    this.wireStart = null;
    this.drag = null;
    this.flows = [];
    this.dotPaths = [];
    this._bindEvents();
    this.render();
    this._tick = this._tick.bind(this);
    requestAnimationFrame(this._tick);
  }

  // ---- editing ---------------------------------------------------------------------------------
  snapshot() {
    return JSON.stringify(this.design);
  }

  commit(before) {
    // Called after every edit with the state from before it, so undo can go back.
    if (before === this.snapshot()) return;
    this.undoStack.push(before);
    if (this.undoStack.length > 200) this.undoStack.shift();
    this.redoStack = [];
    this.changed();
  }

  changed() {
    this.render();
    this.onChange(this.netlist());
  }

  undo() {
    if (!this.undoStack.length) return;
    this.redoStack.push(this.snapshot());
    this.load(JSON.parse(this.undoStack.pop()), false);
  }

  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(this.snapshot());
    this.load(JSON.parse(this.redoStack.pop()), false);
  }

  load(design, recordUndo = true) {
    const before = this.snapshot();
    this.design = { parts: design.parts.map((p) => ({ rot: 0, ...p })), wires: design.wires.map((w) => ({ ...w })) };
    this.nextId = Math.max(0, ...this.design.parts.map((p) => p.id)) + 1;
    this.selected = null;
    this.results = null;
    this.probes = [];
    if (recordUndo) this.commit(before);
    else this.changed();
  }

  clear() {
    this.load({ parts: [], wires: [] });
  }

  setMode(mode, placeType = null) {
    this.mode = mode;
    this.placeType = placeType;
    this.wireStart = null;
    this.svg.dataset.mode = mode;
    this.render();
  }

  addPart(type, x, y) {
    const before = this.snapshot();
    const info = PART_TYPES[type];
    const name = nextName(this.design, type === "GND" ? "GND" : info.letter);
    const part = { id: this.nextId++, type, name, x, y, rot: 0, value: info.value };
    this.design.parts.push(part);
    this.select({ kind: "part", id: part.id });
    this.commit(before);
    return part;
  }

  updatePart(id, changes) {
    const before = this.snapshot();
    Object.assign(this.part(id), changes);
    this.commit(before);
  }

  part(id) {
    return this.design.parts.find((p) => p.id === id);
  }

  rotateSelected() {
    if (!this.selected || this.selected.kind !== "part") return;
    const before = this.snapshot();
    const p = this.part(this.selected.id);
    p.rot = ((p.rot || 0) + 90) % 360;
    this.commit(before);
  }

  deleteSelected() {
    if (!this.selected) return;
    const before = this.snapshot();
    if (this.selected.kind === "part") {
      this.design.parts = this.design.parts.filter((p) => p.id !== this.selected.id);
    } else {
      this.design.wires.splice(this.selected.id, 1);
    }
    this.select(null);
    this.commit(before);
  }

  select(selection) {
    this.selected = selection;
    this.onSelect(selection && selection.kind === "part" ? this.part(selection.id) : null);
    this.render();
  }

  netlist(title) {
    return toNetlist(this.design, title);
  }

  // ---- results ---------------------------------------------------------------------------------
  setResults(result) {
    this.results = result && result.ok ? result : null;
    this.flows = [];
    if (this.results) {
      try {
        this.flows = wireCurrents(this.design, buildNets(this.design), this.results.parts);
      } catch (error) {
        this.flows = [];
      }
    }
    this.render();
  }

  setHighlight(names) {
    this.highlight = new Set((names || []).map((n) => n.toLowerCase()));
    this.render();
  }

  setProbes(probes) {
    this.probes = probes;
    this.render();
  }

  // ---- drawing ---------------------------------------------------------------------------------
  render() {
    const nets = buildNets(this.design);
    const voltages = this.results ? this.results.nodes : null;
    const partResults = new Map(this.results ? this.results.parts.map((p) => [p.name.toLowerCase(), p]) : []);
    const out = [];

    this.design.wires.forEach((w, index) => {
      const net = nets.wireNet(w);
      const selected = this.selected && this.selected.kind === "wire" && this.selected.id === index;
      const tip = voltages && net in voltages ? `node ${net}: ${formatEng(voltages[net], "V")}` : net === "0" ? "ground (0 V)" : `node ${net}`;
      out.push(`<line class="wire${selected ? " selected" : ""}" data-wire="${index}" x1="${w.x1 * G}" y1="${w.y1 * G}" x2="${w.x2 * G}" y2="${w.y2 * G}"><title>${tip}</title></line>`);
    });

    // Junction dots where three or more wire ends or pins meet.
    const count = new Map();
    const bump = (x, y) => count.set(`${x},${y}`, (count.get(`${x},${y}`) || 0) + 1);
    this.design.wires.forEach((w) => { bump(w.x1, w.y1); bump(w.x2, w.y2); });
    this.design.parts.forEach((p) => pinPositions(p).forEach(([x, y]) => bump(x, y)));
    for (const [k, n] of count) {
      if (n >= 3) {
        const [x, y] = k.split(",").map(Number);
        out.push(`<circle class="junction" cx="${x * G}" cy="${y * G}" r="3.5"/>`);
      }
    }

    for (const p of this.design.parts) {
      const result = partResults.get(p.name.toLowerCase());
      const classes = ["part"];
      if (this.selected && this.selected.kind === "part" && this.selected.id === p.id) classes.push("selected");
      if (this.highlight.has(p.name.toLowerCase())) classes.push("highlight");
      if (result && result.rating && result.power > result.rating) classes.push("hot");
      const tip = this._partTip(p, result);
      out.push(`<g class="${classes.join(" ")}" data-part="${p.id}" transform="translate(${p.x * G},${p.y * G}) rotate(${p.rot || 0})">`);
      out.push(`<rect class="hit" x="-44" y="-44" width="88" height="88"/>${SYMBOLS[p.type]}<title>${tip}</title></g>`);
      if (p.type !== "GND") {
        const vertical = (p.rot || 0) % 180 !== 0 || ["V", "I"].includes(p.type);
        const [lx, ly, anchor] = vertical ? [p.x * G + 20, p.y * G - 4, "start"] : [p.x * G, p.y * G - 24, "middle"];
        // Long waveform specs would run into neighbouring labels; the tooltip has the full text.
        let value = p.value || "";
        if (value.length > 14) value = value.includes("(") ? `${value.split("(")[0]}(…)` : value.split(/\s+/)[0];
        value = value ? ` ${value}` : "";
        out.push(`<text class="label" x="${lx}" y="${ly}" text-anchor="${anchor}">${escapeHtml(p.name + value)}</text>`);
      }
      for (const [x, y] of pinPositions(p)) out.push(`<circle class="pin" cx="${x * G}" cy="${y * G}" r="2.5"/>`);
    }

    // Node voltages, written once per node next to one of its points.
    if (voltages) {
      const labeled = new Set();
      const spots = [...this.design.wires.map((w) => [w.x1, w.y1]), ...this.design.parts.flatMap((p) => pinPositions(p))];
      for (const [x, y] of spots) {
        const net = nets.netAt(x, y);
        if (labeled.has(net) || !(net in voltages)) continue;
        labeled.add(net);
        out.push(`<text class="voltage" x="${x * G + 4}" y="${y * G - 6}">${formatEng(voltages[net], "V")}</text>`);
      }
    }

    // Probe markers.
    const colors = ["#f5c518", "#2ec4ff", "#ff5fa2", "#7CFC00"];
    this.probes.forEach((probe, k) => {
      const spot = [...this.design.wires.map((w) => [w.x1, w.y1]), ...this.design.parts.flatMap((p) => pinPositions(p))]
        .find(([x, y]) => nets.netAt(x, y) === probe);
      if (spot) out.push(`<circle class="probe" cx="${spot[0] * G}" cy="${spot[1] * G}" r="7" style="stroke:${colors[k % 4]}"/><text class="probe-label" x="${spot[0] * G - 6}" y="${spot[1] * G + 20}" fill="${colors[k % 4]}">CH${k + 1}</text>`);
    });

    if (this.wireStart && this.wirePreview) {
      const [sx, sy] = this.wireStart;
      const [ex, ey] = this.wirePreview;
      out.push(`<polyline class="wire preview" points="${sx * G},${sy * G} ${ex * G},${sy * G} ${ex * G},${ey * G}"/>`);
    }
    out.push(`<g id="dots"></g>`);
    this.svg.querySelector("#content").innerHTML = out.join("");
    this._prepareDots();
  }

  _partTip(p, result) {
    const info = PART_TYPES[p.type];
    let tip = `${p.name}: ${info.label}${p.value ? " " + p.value : ""}`;
    if (result) {
      tip += `\ncurrent ${formatEng(result.currents[0], "A")}, power ${formatEng(result.power, "W")}`;
      if (result.region) tip += `\n${result.region}`;
      if (result.rating && result.power > result.rating) tip += `\nOVERHEATING: rated ${formatEng(result.rating, "W")}`;
    }
    return escapeHtml(tip);
  }

  // ---- moving current ------------------------------------------------------------------------------
  // Dots slide along wires and through parts at a speed that grows with the log of the current,
  // so both microamps and amps are visible. Direction follows the conventional current.
  _prepareDots() {
    this.dotPaths = [];
    const add = (x1, y1, x2, y2, current) => {
      if (!Number.isFinite(current) || Math.abs(current) < 1e-9) return;
      const length = Math.hypot(x2 - x1, y2 - y1) * G;
      if (length < 1) return;
      const speed = Math.sign(current) * Math.min(140, 20 * Math.log10(Math.abs(current) / 1e-9));
      this.dotPaths.push({ x1: x1 * G, y1: y1 * G, x2: x2 * G, y2: y2 * G, length, speed, dots: [] });
    };
    for (const f of this.flows) add(f.x1, f.y1, f.x2, f.y2, f.current);
    if (this.results) {
      const byName = new Map(this.results.parts.map((r) => [r.name.toLowerCase(), r]));
      for (const p of this.design.parts) {
        const result = byName.get(p.name.toLowerCase());
        if (!result) continue;
        const pins = pinPositions(p);
        if (pins.length === 2) add(pins[0][0], pins[0][1], pins[1][0], pins[1][1], result.currents[0]);
        else pins.forEach(([x, y], k) => add(x, y, p.x, p.y, result.currents[k] || 0));
      }
    }
    const layer = this.svg.querySelector("#dots");
    for (const path of this.dotPaths) {
      const n = Math.max(1, Math.floor(path.length / 16));
      for (let k = 0; k < n; k++) {
        const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        dot.setAttribute("r", "2.6");
        dot.setAttribute("class", "dot");
        layer.appendChild(dot);
        path.dots.push(dot);
      }
    }
  }

  _tick(time) {
    const t = time / 1000;
    for (const path of this.dotPaths) {
      const n = path.dots.length;
      path.dots.forEach((dot, k) => {
        if (!this.animate) { dot.setAttribute("visibility", "hidden"); return; }
        dot.setAttribute("visibility", "visible");
        let s = ((path.speed * t + (k * path.length) / n) % path.length + path.length) % path.length;
        const f = s / path.length;
        dot.setAttribute("cx", path.x1 + (path.x2 - path.x1) * f);
        dot.setAttribute("cy", path.y1 + (path.y2 - path.y1) * f);
      });
    }
    requestAnimationFrame(this._tick);
  }

  // ---- input -------------------------------------------------------------------------------------
  _point(event) {
    const box = this.svg.getBoundingClientRect();
    return [Math.round((event.clientX - box.left) / G), Math.round((event.clientY - box.top) / G)];
  }

  _bindEvents() {
    this.svg.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      const [x, y] = this._point(event);
      const partEl = event.target.closest("[data-part]");
      const wireEl = event.target.closest("[data-wire]");
      if (this.mode === "place") {
        this.addPart(this.placeType, x, y);
        return;
      }
      if (this.mode === "wire") {
        this._wireClick(x, y);
        return;
      }
      if (this.mode === "probe") {
        const net = buildNets(this.design).netAt(x, y);
        if (net !== undefined) this.onProbe(net);
        return;
      }
      if (partEl) {
        const id = Number(partEl.dataset.part);
        const p = this.part(id);
        this.select({ kind: "part", id });
        this.drag = { id, dx: x - p.x, dy: y - p.y, before: this.snapshot() };
      } else if (wireEl) {
        this.select({ kind: "wire", id: Number(wireEl.dataset.wire) });
      } else {
        this.select(null);
      }
    });

    this.svg.addEventListener("mousemove", (event) => {
      const [x, y] = this._point(event);
      if (this.drag) {
        const p = this.part(this.drag.id);
        if (p.x !== x - this.drag.dx || p.y !== y - this.drag.dy) {
          p.x = x - this.drag.dx;
          p.y = y - this.drag.dy;
          this.render();
        }
      } else if (this.mode === "wire" && this.wireStart) {
        this.wirePreview = [x, y];
        this.render();
      }
    });

    window.addEventListener("mouseup", () => {
      if (this.drag) {
        const before = this.drag.before;
        this.drag = null;
        this.commit(before);
      }
    });

    this.svg.addEventListener("dblclick", () => this._endWire());
    this.svg.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      if (this.mode === "wire") this._endWire();
      else this.setMode("select");
    });

    window.addEventListener("keydown", (event) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
      const ctrl = event.ctrlKey || event.metaKey;
      if (ctrl && event.key.toLowerCase() === "z") { event.preventDefault(); this.undo(); }
      else if (ctrl && event.key.toLowerCase() === "y") { event.preventDefault(); this.redo(); }
      else if (event.key === "r" || event.key === "R") this.rotateSelected();
      else if (event.key === "Delete" || event.key === "Backspace") this.deleteSelected();
      else if (event.key === "Escape") { this._endWire(); this.setMode("select"); }
      else if (event.key === "w" || event.key === "W") this.setMode("wire");
    });
  }

  _wireClick(x, y) {
    if (!this.wireStart) {
      this.wireStart = [x, y];
      this.wirePreview = [x, y];
      this.wireBefore = this.snapshot();
      return;
    }
    const [sx, sy] = this.wireStart;
    // An L-shaped route: across first, then up or down.
    if (x !== sx) this.design.wires.push({ x1: sx, y1: sy, x2: x, y2: sy });
    if (y !== sy) this.design.wires.push({ x1: x, y1: sy, x2: x, y2: y });
    const endsOnSomething = this.design.parts.some((p) => pinPositions(p).some(([px, py]) => px === x && py === y))
      || this.design.wires.slice(0, -1).some((w) => (w.x1 === x && w.y1 === y) || (w.x2 === x && w.y2 === y));
    this.wireStart = [x, y];
    if (endsOnSomething && (x !== sx || y !== sy)) this._endWire();
    else this.render();
  }

  _endWire() {
    if (this.wireStart) {
      this.wireStart = null;
      this.wirePreview = null;
      this.commit(this.wireBefore);
    }
  }
}

export function escapeHtml(text) {
  return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

export function symbolSvg(type, size = 40) {
  // A small icon of a part for the palette.
  return `<svg viewBox="-46 -46 92 92" width="${size}" height="${size}"><g class="part">${SYMBOLS[type]}</g></svg>`;
}
