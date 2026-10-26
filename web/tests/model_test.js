// Tests for web/editor/model.js. Run with: python tools/run_js_tests.py
// (any JavaScript engine works; the runner strips the module syntax and calls each test).

function assert(condition, message) {
  if (!condition) throw new Error("assertion failed: " + message);
}

function close(a, b, tol = 1e-9) {
  return Math.abs(a - b) <= tol * Math.max(1, Math.abs(b));
}

// A divider: V1 at x=0 (pins (0,-2) top, (0,2) bottom), R1 across the top, R2 down the right side.
function divider() {
  return {
    parts: [
      { id: 1, type: "V", name: "V1", x: 0, y: 0, rot: 0, value: "10" },
      { id: 2, type: "R", name: "R1", x: 4, y: -4, rot: 0, value: "1k" },
      { id: 3, type: "R", name: "R2", x: 8, y: 0, rot: 90, value: "1k" },
      { id: 4, type: "GND", name: "GND1", x: 4, y: 4, rot: 0, value: "" },
    ],
    wires: [
      { x1: 0, y1: -2, x2: 0, y2: -4 }, { x1: 0, y1: -4, x2: 2, y2: -4 },   // V1+ to R1 left
      { x1: 6, y1: -4, x2: 8, y2: -4 }, { x1: 8, y1: -4, x2: 8, y2: -2 },   // R1 right to R2 top
      { x1: 0, y1: 2, x2: 0, y2: 4 }, { x1: 0, y1: 4, x2: 8, y2: 4 },       // ground rail
      { x1: 8, y1: 4, x2: 8, y2: 2 },                                      // R2 bottom
    ],
  };
}

const tests = {
  rotation() {
    assert(rotatePoint([2, 0], 90).join() === "0,2", "90 degrees");
    assert(rotatePoint([2, 0], 180).join() === "-2,0", "180 degrees");
    assert(rotatePoint([2, 0], 270).join() === "0,-2", "270 degrees");
    const pins = pinPositions({ type: "R", x: 8, y: 0, rot: 90 });
    assert(pins[0].join() === "8,-2" && pins[1].join() === "8,2", "rotated resistor pins");
  },

  netsFromWires() {
    const nets = buildNets(divider());
    assert(nets.pinNets.get(1).join() === "1,0", "V1 nets " + nets.pinNets.get(1));
    assert(nets.pinNets.get(2).join() === "1,2", "R1 nets " + nets.pinNets.get(2));
    assert(nets.pinNets.get(3).join() === "2,0", "R2 nets " + nets.pinNets.get(3));
  },

  tJunctionJoinsNets() {
    // A wire ending in the middle of another wire connects to it.
    const design = {
      parts: [
        { id: 1, type: "R", name: "R1", x: 0, y: 0, rot: 0, value: "1k" },
        { id: 2, type: "R", name: "R2", x: 4, y: 4, rot: 90, value: "1k" },
      ],
      wires: [{ x1: 2, y1: 0, x2: 8, y2: 0 }, { x1: 4, y1: 2, x2: 4, y2: 0 }],
    };
    const nets = buildNets(design);
    assert(nets.pinNets.get(1)[1] === nets.pinNets.get(2)[0], "T junction");
  },

  netlistRoundTrip() {
    const text = toNetlist(divider(), "test");
    assert(text.includes("V1 1 0 10"), text);
    assert(text.includes("R1 1 2 1k"), text);
    assert(text.includes("R2 2 0 1k"), text);
    const back = fromNetlist(text);
    assert(back.parts.length === 4 && back.wires.length === 7, "same parts and wires");
    assert(toNetlist(back, "test") === text, "round trip is exact");
  },

  autoLayoutIsElectricallyRight() {
    const design = fromNetlist("V1 in 0 10\nR1 in out 1k\nR2 out 0 1k\nD1 out 0 led_red\nQ1 c b 0 2n3906\n");
    const text = toNetlist(design);
    const lines = text.split("\n").filter((l) => /^[A-Z]/.test(l));
    const v1 = lines.find((l) => l.startsWith("V1")).split(" ");
    const r1 = lines.find((l) => l.startsWith("R1")).split(" ");
    const r2 = lines.find((l) => l.startsWith("R2")).split(" ");
    assert(v1[2] === "0" && r2[2] === "0", "ground found");
    assert(v1[1] === r1[1] && r1[2] === r2[1], "same connections as the netlist");
    assert(design.parts.find((p) => p.name === "D1").type === "LED", "LED type");
    assert(design.parts.find((p) => p.name === "Q1").type === "PNP", "PNP type");
  },

  wireCurrentsFollowKcl() {
    const design = divider();
    const nets = buildNets(design);
    // What the engine reports for this divider: 5 mA around the loop.
    const parts = [
      { name: "V1", currents: [-5e-3, 5e-3] },
      { name: "R1", currents: [5e-3, -5e-3] },
      { name: "R2", currents: [5e-3, -5e-3] },
      { name: "GND1", currents: [0] },
    ];
    const flows = wireCurrents(design, nets, parts);
    // The ground symbol sits in the middle of the ground rail, which splits that wire in two.
    assert(flows.length === 8, "one flow per wire piece");
    // Every wire carries the loop current of 5 mA.
    for (const f of flows) assert(close(Math.abs(f.current), 5e-3), JSON.stringify(f));
    // The wire from V1+ (0,-2) up to (0,-4) carries current away from the source.
    const first = flows.find((f) => f.x1 === 0 && f.y1 === -2);
    assert(close(first.current, 5e-3), "direction " + first.current);
  },

  numbers() {
    assert(formatEng(1500, "Ω") === "1.5 kΩ", formatEng(1500, "Ω"));
    assert(formatEng(-0.005, "A") === "-5 mA", formatEng(-0.005, "A"));
    assert(formatEng(0, "V") === "0 V", "zero");
    assert(close(parseValue("4.7k"), 4700) && close(parseValue("10meg"), 1e7) && close(parseValue("1M"), 1e-3), "parse");
    assert(parseValue("abc") === null, "bad value");
    assert(mainValue("330 rating=0.25") === 330 && mainValue("PULSE(0 5 1m)") === null, "leading value");
    assert(spiceValue(4700) === "4.7k" && spiceValue(2.2e-6) === "2.2u" && spiceValue(1e6) === "1meg", "spice values");
  },

  names() {
    assert(nextName(divider(), "R") === "R3", "next resistor name");
  },
};
