// Tests for the board-sample parser in web/scope/serial.js.

function assert(condition, message) {
  if (!condition) throw new Error("assertion failed: " + message);
}

const tests = {
  parsesSamples() {
    const s = parseLine("1500,1023,0,512", 5.0, 10);
    assert(s.t === 1.5, "time in seconds");
    assert(Math.abs(s.volts[0] - 5) < 1e-12 && s.volts[1] === 0, "full scale and zero");
    assert(Math.abs(s.volts[2] - 2.502443792766373) < 1e-9, "mid scale");
  },
  esp32Scale() {
    const s = parseLine("0,4095", 3.3, 12);
    assert(Math.abs(s.volts[0] - 3.3) < 1e-12, "12-bit full scale");
  },
  ignoresJunk() {
    assert(parseLine("# MiniSpice probe ready") === null, "banner");
    assert(parseLine("") === null && parseLine("12,abc") === null && parseLine("12") === null, "junk");
  },
};
