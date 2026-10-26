// Tests for web/breadboard/layout.js.

function assert(condition, message) {
  if (!condition) throw new Error("assertion failed: " + message);
}

function divider() {
  return fromNetlist(`* divider
* @part V1 V 4 8 0
* @part R1 R 8 4 0
* @part R2 R 12 8 90
* @part GND1 GND 8 12 0
* @wire 4 6 4 4
* @wire 4 4 6 4
* @wire 10 4 12 4
* @wire 12 4 12 6
* @wire 4 10 4 12
* @wire 4 12 12 12
* @wire 12 12 12 10
V1 1 0 10
R1 1 2 4.7k
R2 2 0 1k
`);
}

const tests = {
  colorCode() {
    assert(colorBands(4700).join() === "yellow,violet,red,gold", colorBands(4700).join());
    assert(colorBands(1000).join() === "brown,black,red,gold", colorBands(1000).join());
    assert(colorBands(330).join() === "orange,orange,brown,gold", colorBands(330).join());
    assert(colorBands(10).join() === "brown,black,black,gold", colorBands(10).join());
  },

  supplyAndGroundUseTheRails() {
    const plan = planBreadboard(divider());
    assert(plan.supply && plan.supply.source.name === "V1", "V1 is the supply");
    assert(plan.railNets.get("0") === "-" && plan.railNets.get("1") === "+", "rails");
    assert(plan.strips.size === 1 && plan.strips.has("2"), "only the middle node needs a strip");
  },

  partsShareTheirNodesStrip() {
    const plan = planBreadboard(divider());
    const r1 = plan.placements.find((p) => p.part.name === "R1");
    const r2 = plan.placements.find((p) => p.part.name === "R2");
    assert(r1.legs[0].rail === "+", "R1 top leg on the + rail");
    assert(r1.legs[1].col === r2.legs[0].col, "R1 and R2 meet in the same column strip");
    assert(r1.legs[1].row !== r2.legs[0].row, "but in different holes");
    assert(r2.legs[1].rail === "-", "R2 to ground rail");
  },

  instructionsAreSpecific() {
    const text = planBreadboard(divider()).instructions.join("\n");
    assert(text.includes("Set it to 10 V"), text);
    assert(text.includes("R1 (resistor, 4.7 kΩ)") && text.includes("yellow, violet, red, gold"), text);
    assert(/hole 5[a-e]/.test(text), text);
  },
};
