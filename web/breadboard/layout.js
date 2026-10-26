// Plans how to build a design on a real solderless breadboard (Phase 35).
//
// A breadboard has numbered columns. In each column, holes a-e are joined underneath, and so are
// f-j (the gap down the middle separates them). Along the top and bottom run power rails: one
// red (+) and one blue (-). So every circuit node needs its own column strip, and every part's
// legs go into the strips of the nodes it touches.

import { buildNets, formatEng, mainValue, PART_TYPES } from "../editor/model.js";

export const COLUMNS = 63;
export const TOP_ROWS = ["a", "b", "c", "d", "e"];
export const BOTTOM_ROWS = ["f", "g", "h", "i", "j"];

// Resistor color code: digit colors, then the multiplier.
const BAND_COLORS = ["black", "brown", "red", "orange", "yellow", "green", "blue", "violet", "gray", "white"];

export function colorBands(ohms) {
  // Two significant digits and a multiplier, the 4-band code on most hobby resistors.
  if (!(ohms > 0)) return [];
  let exponent = Math.floor(Math.log10(ohms)) - 1;
  let digits = Math.round(ohms / Math.pow(10, exponent));
  if (digits >= 100) { digits = Math.round(digits / 10); exponent += 1; }
  if (exponent < 0 || exponent > 9) return [];
  return [BAND_COLORS[Math.floor(digits / 10)], BAND_COLORS[digits % 10], BAND_COLORS[exponent], "gold"];
}

function railFor(design, nets) {
  // The supply rail is the + side of the first voltage source whose - side is ground.
  for (const part of design.parts) {
    if (part.type !== "V") continue;
    const [plus, minus] = nets.pinNets.get(part.id);
    if (minus === "0" && plus !== "0") return { net: plus, source: part };
  }
  return null;
}

export function planBreadboard(design) {
  const nets = buildNets(design);
  const supply = railFor(design, nets);
  const strips = new Map(); // net -> {col, rows, used}
  const railNets = new Map([["0", "-"]]);
  if (supply) railNets.set(supply.net, "+");

  const allNets = [];
  for (const part of design.parts) {
    for (const net of nets.pinNets.get(part.id)) if (!allNets.includes(net)) allNets.push(net);
  }
  // Give each other node its own strip, spaced so parts have room between them.
  let col = 5;
  let bottom = false;
  for (const net of allNets) {
    if (railNets.has(net)) continue;
    if (col > COLUMNS - 3) {
      if (bottom) throw new Error("This circuit has too many nodes for one breadboard.");
      bottom = true;
      col = 5;
    }
    strips.set(net, { col, rows: bottom ? BOTTOM_ROWS : TOP_ROWS, used: 0 });
    col += 5;
  }

  const placements = [];
  const instructions = [];
  const jumpers = [];
  const hole = (net, nearCol) => {
    // The next free hole in a node's strip, or a rail hole lined up with the other leg.
    if (railNets.has(net)) {
      // Rail legs fan out to the right of the part's strip, so neighbouring parts don't sit on top of each other.
      const rail = railNets.get(net);
      const col = nearCol + 2 + 2 * (placements.length % 4);
      return { col: Math.max(1, Math.min(COLUMNS, col)), row: rail === "+" ? "+" : "-", rail };
    }
    const strip = strips.get(net);
    const row = strip.rows[Math.min(strip.used, strip.rows.length - 1)];
    strip.used += 1;
    return { col: strip.col, row };
  };
  const where = (h) => (h.rail ? `the ${h.rail === "+" ? "red (+)" : "blue (−)"} rail at column ${h.col}` : `hole ${h.col}${h.row}`);

  if (supply) {
    instructions.push(`Connect your power supply: + to the red (+) rail, − to the blue (−) rail. Set it to ${supply.source.value} V (that is ${supply.source.name}).`);
  } else {
    instructions.push("Connect your power supply's − to the blue (−) rail: that rail is ground (node 0).");
  }

  for (const part of design.parts) {
    if (part.type === "GND" || (supply && part.id === supply.source.id)) continue;
    const info = PART_TYPES[part.type];
    const partNets = nets.pinNets.get(part.id);
    const near = partNets.map((n) => (strips.has(n) ? strips.get(n).col : null)).find((c) => c !== null) || 3;
    if (part.type === "OPAMP") {
      // An op-amp is an 8-pin chip that straddles the middle gap; its pins reach the nodes by jumpers.
      const c0 = Math.max(...[...strips.values()].map((s) => s.col), 0) + 6;
      const pins = { 2: partNets[1], 3: partNets[0], 6: partNets[2] };
      placements.push({ part, kind: "dip", col: c0, label: `${part.name} op-amp` });
      instructions.push(`${part.name}: an 8-pin op-amp chip (like the LM741) across the middle gap, pin 1 in hole ${c0}f, pins 1-4 along row f and 8-5 along row e.`);
      for (const [pin, net] of Object.entries(pins)) {
        const pinNumber = Number(pin);
        const at = pinNumber <= 4 ? { col: c0 + pinNumber - 1, row: "j" } : { col: c0 + 8 - pinNumber, row: "a" };
        const to = hole(net, at.col);
        jumpers.push({ from: at, to, net });
        instructions.push(`  Jumper from the chip's pin ${pinNumber} (${["", "", "inverting input", "non-inverting input", "", "", "output"][pinNumber]}) strip to ${where(to)}.`);
      }
      instructions.push(`  Power the chip: pin 7 to your + supply and pin 4 to your − supply (an ideal op-amp in the simulation needs no supply, a real one does).`);
      continue;
    }
    const legs = partNets.map((n) => hole(n, near));
    placements.push({ part, kind: part.type, legs, label: `${part.name} ${part.value || ""}`.trim() });
    let text = `${part.name} (${info.label.toLowerCase()}${part.value ? `, ${describeValue(part)}` : ""}): `;
    if (legs.length === 2) {
      text += `${legName(part.type, 0)} in ${where(legs[0])}, ${legName(part.type, 1)} in ${where(legs[1])}.`;
    } else {
      text += legs.map((h, k) => `${legName(part.type, k)} in ${where(h)}`).join(", ") + ".";
    }
    if (part.type === "R") {
      const bands = colorBands(mainValue(part.value));
      if (bands.length) text += ` Color bands: ${bands.join(", ")}.`;
    }
    instructions.push(text);
  }
  return { strips, railNets, placements, jumpers, instructions, supply };
}

function describeValue(part) {
  const info = PART_TYPES[part.type];
  const v = mainValue(part.value);
  return info.numeric && v !== null ? formatEng(v, info.unit) : part.value;
}

function legName(type, k) {
  const names = {
    D: ["anode (long leg)", "cathode (banded end)"],
    LED: ["anode (long leg)", "cathode (short leg, flat side)"],
    NPN: ["collector", "base", "emitter"],
    PNP: ["collector", "base", "emitter"],
    NMOS: ["drain", "gate", "source"],
    PMOS: ["drain", "gate", "source"],
    C: ["+ leg (long leg, if it's an electrolytic)", "− leg"],
    V: ["+ lead", "− lead"],
    I: ["+ lead", "− lead"],
  };
  return (names[type] || ["one leg", "the other leg"])[k] || `leg ${k + 1}`;
}
