// The editor's data model, with no drawing code: parts, wires, which wires form the same node,
// and conversion between a drawing and a netlist. Kept free of the DOM so it can be unit tested.
//
// Coordinates are in grid units (one unit = GRID pixels on screen). A design is
//   { parts: [{id, type, name, x, y, rot, value}], wires: [{x1, y1, x2, y2}] }

export const GRID = 20;

// pins: positions at rotation 0, in the order the netlist line lists the part's nodes.
export const PART_TYPES = {
  R: { letter: "R", label: "Resistor", pins: [[-2, 0], [2, 0]], value: "1k", unit: "Ω", numeric: true },
  C: { letter: "C", label: "Capacitor", pins: [[-2, 0], [2, 0]], value: "1u", unit: "F", numeric: true },
  L: { letter: "L", label: "Inductor", pins: [[-2, 0], [2, 0]], value: "1m", unit: "H", numeric: true },
  V: { letter: "V", label: "Voltage source", pins: [[0, -2], [0, 2]], value: "5", unit: "V", numeric: true },
  I: { letter: "I", label: "Current source", pins: [[0, 2], [0, -2]], value: "1m", unit: "A", numeric: true },
  D: { letter: "D", label: "Diode", pins: [[-2, 0], [2, 0]], value: "d" },
  LED: { letter: "D", label: "LED", pins: [[-2, 0], [2, 0]], value: "led_red" },
  NPN: { letter: "Q", label: "NPN transistor", pins: [[1, -2], [-2, 0], [1, 2]], value: "npn" },
  PNP: { letter: "Q", label: "PNP transistor", pins: [[1, 2], [-2, 0], [1, -2]], value: "pnp" },
  NMOS: { letter: "M", label: "N-channel MOSFET", pins: [[1, -2], [-2, 0], [1, 2]], value: "nmos" },
  PMOS: { letter: "M", label: "P-channel MOSFET", pins: [[1, 2], [-2, 0], [1, -2]], value: "pmos" },
  OPAMP: { letter: "U", label: "Op-amp", pins: [[-2, 1], [-2, -1], [2, 0]], value: "" },
  S: { letter: "S", label: "Switch", pins: [[-2, 0], [2, 0]], value: "ton=1m" },
  GND: { letter: "", label: "Ground", pins: [[0, 0]], value: "" },
};

export function rotatePoint([x, y], rot) {
  // Screen y points down, so a clockwise quarter turn maps (x, y) to (-y, x).
  switch (((rot % 360) + 360) % 360) {
    case 90: return [-y, x];
    case 180: return [-x, -y];
    case 270: return [y, -x];
    default: return [x, y];
  }
}

export function pinPositions(part) {
  return PART_TYPES[part.type].pins.map((p) => {
    const [dx, dy] = rotatePoint(p, part.rot || 0);
    return [part.x + dx, part.y + dy];
  });
}

const key = (x, y) => `${x},${y}`;

function onSegment(px, py, w) {
  // Wires are horizontal or vertical, so "on the segment" is a simple range check.
  if (w.x1 === w.x2 && px === w.x1) {
    return py > Math.min(w.y1, w.y2) && py < Math.max(w.y1, w.y2);
  }
  if (w.y1 === w.y2 && py === w.y1) {
    return px > Math.min(w.x1, w.x2) && px < Math.max(w.x1, w.x2);
  }
  return false;
}

// Union-find: every pin and wire end is a point; wires join their two ends, and a point that
// lands in the middle of a wire (a T junction) joins that wire too.
export function buildNets(design) {
  const parent = new Map();
  const find = (k) => {
    if (!parent.has(k)) parent.set(k, k);
    let r = k;
    while (parent.get(r) !== r) r = parent.get(r);
    while (parent.get(k) !== r) { const next = parent.get(k); parent.set(k, r); k = next; }
    return r;
  };
  const union = (a, b) => { parent.set(find(a), find(b)); };

  const pinPoints = [];
  for (const part of design.parts) {
    pinPositions(part).forEach(([x, y], index) => {
      pinPoints.push({ part, index, x, y });
      find(key(x, y));
    });
  }
  for (const w of design.wires) union(key(w.x1, w.y1), key(w.x2, w.y2));
  const points = [...pinPoints.map((p) => [p.x, p.y]), ...design.wires.flatMap((w) => [[w.x1, w.y1], [w.x2, w.y2]])];
  for (const w of design.wires) {
    for (const [x, y] of points) {
      if (onSegment(x, y, w)) union(key(x, y), key(w.x1, w.y1));
    }
  }

  // Name the nets: anything touching a ground symbol is "0", the rest 1, 2, 3, ... in part order.
  const names = new Map();
  for (const p of pinPoints) {
    if (p.part.type === "GND") names.set(find(key(p.x, p.y)), "0");
  }
  let next = 1;
  for (const p of pinPoints) {
    const root = find(key(p.x, p.y));
    if (!names.has(root)) names.set(root, String(next++));
  }
  for (const w of design.wires) {
    const root = find(key(w.x1, w.y1));
    if (!names.has(root)) names.set(root, String(next++));
  }
  const netAt = (x, y) => names.get(find(key(x, y)));
  const pinNets = new Map();
  for (const part of design.parts) {
    pinNets.set(part.id, pinPositions(part).map(([x, y]) => netAt(x, y)));
  }
  return { netAt, pinNets, wireNet: (w) => netAt(w.x1, w.y1) };
}

// ---- netlists -----------------------------------------------------------------------------------

export function toNetlist(design, title = "MiniSpice editor design") {
  const nets = buildNets(design);
  const lines = [`* ${title}`];
  // Layout comments let the netlist turn back into exactly the same drawing.
  for (const p of design.parts) lines.push(`* @part ${p.name} ${p.type} ${p.x} ${p.y} ${p.rot || 0}`);
  for (const w of design.wires) lines.push(`* @wire ${w.x1} ${w.y1} ${w.x2} ${w.y2}`);
  for (const p of design.parts) {
    if (p.type === "GND") continue;
    const nodes = nets.pinNets.get(p.id);
    lines.push(`${p.name} ${nodes.join(" ")} ${p.value || ""}`.trim());
  }
  lines.push(".end");
  return lines.join("\n") + "\n";
}

const NODE_COUNT = { R: 2, C: 2, L: 2, V: 2, I: 2, D: 2, S: 2, Q: 3, M: 3, U: 3 };

function typeFor(letter, value) {
  const v = (value || "").toLowerCase();
  if (letter === "D") return v.startsWith("led") ? "LED" : "D";
  if (letter === "Q") return v.includes("pnp") || v === "2n3906" ? "PNP" : "NPN";
  if (letter === "M") return v.includes("pmos") ? "PMOS" : "NMOS";
  if (letter === "U") return "OPAMP";
  return letter;
}

export function fromNetlist(text) {
  const elements = [];
  const layout = new Map();
  const wires = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    let m = line.match(/^\*\s*@part\s+(\S+)\s+(\S+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)/);
    if (m) { layout.set(m[1].toLowerCase(), { name: m[1], type: m[2], x: +m[3], y: +m[4], rot: +m[5] }); continue; }
    m = line.match(/^\*\s*@wire\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)/);
    if (m) { wires.push({ x1: +m[1], y1: +m[2], x2: +m[3], y2: +m[4] }); continue; }
    if (!line || line.startsWith("*") || line.startsWith(".")) continue;
    const tokens = line.split(/\s+/);
    const letter = tokens[0][0].toUpperCase();
    const count = NODE_COUNT[letter];
    if (!count) throw new Error(`The editor can't draw '${tokens[0]}' (only R, C, L, V, I, D, S, Q, M and U parts).`);
    let nodes = tokens.slice(1, 1 + count);
    let rest = tokens.slice(1 + count);
    if (letter === "M" && rest.length > 1 && !/=/.test(rest[0])) rest = rest.slice(1); // 4-node MOSFET: drop the body
    elements.push({ name: tokens[0], letter, nodes: nodes.map((n) => (["0", "gnd"].includes(n.toLowerCase()) ? "0" : n.toLowerCase())), value: rest.join(" ") });
  }

  const parts = [];
  let id = 1;
  if (layout.size) {
    for (const item of layout.values()) {
      const element = elements.find((e) => e.name.toLowerCase() === item.name.toLowerCase());
      parts.push({ id: id++, type: item.type, name: item.name, x: item.x, y: item.y, rot: item.rot, value: element ? element.value : "" });
    }
    return { parts, wires };
  }
  return autoLayout(elements);
}

// Without layout comments, place the parts in a grid and join each node's pins with wires.
// The result is untidy but electrically identical to the netlist; the user can then tidy it.
function autoLayout(elements) {
  const parts = [];
  const wires = [];
  const pinsByNet = new Map();
  let id = 1;
  elements.forEach((e, k) => {
    const type = typeFor(e.letter, e.value);
    const part = { id: id++, type, name: e.name, x: 4 + (k % 5) * 8, y: 4 + Math.floor(k / 5) * 8, rot: 0, value: e.value };
    parts.push(part);
    pinPositions(part).forEach((pos, index) => {
      const net = e.nodes[index];
      if (!pinsByNet.has(net)) pinsByNet.set(net, []);
      pinsByNet.get(net).push(pos);
    });
  });
  for (const [net, pins] of pinsByNet) {
    if (net === "0") {
      pins.forEach(([x, y]) => {
        const g = { id: id++, type: "GND", name: `GND${id}`, x, y: y + 2, rot: 0, value: "" };
        parts.push(g);
        wires.push({ x1: x, y1: y, x2: x, y2: y + 2 });
      });
      continue;
    }
    for (let k = 1; k < pins.length; k++) {
      const [ax, ay] = pins[k - 1];
      const [bx, by] = pins[k];
      // An L-shaped route: across, then down.
      if (ax !== bx) wires.push({ x1: ax, y1: ay, x2: bx, y2: ay });
      if (ay !== by) wires.push({ x1: bx, y1: ay, x2: bx, y2: by });
    }
  }
  return { parts, wires };
}

export function nextName(design, letter) {
  let n = 1;
  const taken = new Set(design.parts.map((p) => p.name.toLowerCase()));
  while (taken.has(`${letter}${n}`.toLowerCase())) n++;
  return `${letter}${n}`;
}

// ---- current in the wires -------------------------------------------------------------------------

// The engine reports the current into every part terminal, but a wire's current depends on how the
// wires of a node are drawn. Within one node the wires form a graph whose pins each take or give a
// known current; on a tree that fixes every wire's current (work inward from the leaves). If the
// drawing has loops, the extra wires of each loop are treated as carrying nothing.
export function wireCurrents(design, nets, partsResult) {
  const terminalCurrent = new Map(); // "x,y" -> current flowing out of the node into parts there
  const byName = new Map(partsResult.map((p) => [p.name.toLowerCase(), p]));
  for (const part of design.parts) {
    const result = byName.get(part.name.toLowerCase());
    if (!result) continue;
    pinPositions(part).forEach(([x, y], index) => {
      const k = key(x, y);
      terminalCurrent.set(k, (terminalCurrent.get(k) || 0) + (result.currents[index] || 0));
    });
  }

  // Split wires at T junctions so every graph edge joins two points with nothing in between.
  const allPoints = [...terminalCurrent.keys()].map((k) => k.split(",").map(Number));
  for (const w of design.wires) allPoints.push([w.x1, w.y1], [w.x2, w.y2]);
  const edges = [];
  for (const w of design.wires) {
    const inner = allPoints.filter(([x, y]) => onSegment(x, y, w));
    const along = [[w.x1, w.y1], ...inner, [w.x2, w.y2]];
    along.sort((a, b) => (a[0] - w.x1) ** 2 + (a[1] - w.y1) ** 2 - ((b[0] - w.x1) ** 2 + (b[1] - w.y1) ** 2));
    for (let i = 1; i < along.length; i++) {
      const a = key(...along[i - 1]);
      const b = key(...along[i]);
      if (a !== b) edges.push({ a, b, x1: along[i - 1][0], y1: along[i - 1][1], x2: along[i][0], y2: along[i][1], current: 0 });
    }
  }
  const adjacent = new Map();
  edges.forEach((e, index) => {
    for (const [p, q] of [[e.a, e.b], [e.b, e.a]]) {
      if (!adjacent.has(p)) adjacent.set(p, []);
      adjacent.get(p).push({ to: q, index });
    }
  });

  const visited = new Set();
  for (const start of adjacent.keys()) {
    if (visited.has(start)) continue;
    // Breadth-first spanning tree of this node's wires.
    const order = [start];
    const parentEdge = new Map([[start, null]]);
    visited.add(start);
    for (let i = 0; i < order.length; i++) {
      for (const { to, index } of adjacent.get(order[i])) {
        if (!visited.has(to)) {
          visited.add(to);
          parentEdge.set(to, { from: order[i], index });
          order.push(to);
        }
      }
    }
    // Leaves first: the current a subtree's pins draw must arrive through the edge above it.
    const demand = new Map(order.map((p) => [p, terminalCurrent.get(p) || 0]));
    for (let i = order.length - 1; i > 0; i--) {
      const point = order[i];
      const { from, index } = parentEdge.get(point);
      const edge = edges[index];
      const flowTowardPoint = demand.get(point);
      // Positive edge.current means flow from (x1, y1) to (x2, y2).
      edge.current = edge.b === point ? flowTowardPoint : -flowTowardPoint;
      demand.set(from, demand.get(from) + flowTowardPoint);
    }
  }
  return edges.map(({ x1, y1, x2, y2, current }) => ({ x1, y1, x2, y2, current }));
}

// ---- numbers --------------------------------------------------------------------------------------

const PREFIXES = [[1e12, "T"], [1e9, "G"], [1e6, "M"], [1e3, "k"], [1, ""], [1e-3, "m"], [1e-6, "µ"], [1e-9, "n"], [1e-12, "p"], [1e-15, "f"]];

export function formatEng(value, unit = "", digits = 4) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  if (!Number.isFinite(value)) return `${value} ${unit}`.trim();
  let v = Number(value.toPrecision(digits));
  if (Math.abs(v) < 5e-16) return `0 ${unit}`.trim();
  let scale = 1e-15;
  let prefix = "f";
  for (const [s, p] of PREFIXES) {
    if (Math.abs(v) >= s) { scale = s; prefix = p; break; }
  }
  const mantissa = Number((v / scale).toPrecision(digits));
  return `${mantissa} ${prefix}${unit}`.trim();
}

const SUFFIXES = [["meg", 1e6], ["t", 1e12], ["g", 1e9], ["k", 1e3], ["m", 1e-3], ["u", 1e-6], ["µ", 1e-6], ["n", 1e-9], ["p", 1e-12], ["f", 1e-15]];

export function parseValue(text) {
  const m = String(text).trim().match(/^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Zµ%]*)$/);
  if (!m) return null;
  let value = parseFloat(m[1]);
  const letters = m[2].toLowerCase();
  if (letters.startsWith("%")) return value / 100;
  for (const [s, scale] of SUFFIXES) {
    if (letters.startsWith(s)) return value * scale;
  }
  return value;
}

export function mainValue(text) {
  // The number at the start of a part's value: "330 rating=0.25" -> 330. Null if it isn't a number.
  return parseValue(String(text || "").trim().split(/\s+/)[0]);
}

export function spiceValue(value) {
  // The shortest SPICE spelling of a number: 4700 -> "4.7k". Note SPICE's M is milli, so mega is "meg".
  const table = [[1e9, "g"], [1e6, "meg"], [1e3, "k"], [1, ""], [1e-3, "m"], [1e-6, "u"], [1e-9, "n"], [1e-12, "p"]];
  if (value === 0) return "0";
  for (const [s, p] of table) {
    if (Math.abs(value) >= s) return `${Number((value / s).toPrecision(4))}${p}`;
  }
  return String(value);
}
