// Live link to a microcontroller (Phase 34) through the Web Serial API (Chrome and Edge).
//
// The firmware in firmware/minispice_probe prints one line per sample:
//   t_ms,a0,a1,a2,a3        (raw ADC counts)
// This reader turns those lines into volts and hands each sample to a callback.

export class BoardLink {
  constructor({ vref = 5.0, bits = 10, baud = 115200, onSample = () => {}, onStatus = () => {} } = {}) {
    this.vref = vref;
    this.bits = bits;
    this.baud = baud;
    this.onSample = onSample;
    this.onStatus = onStatus;
    this.port = null;
    this.reading = false;
  }

  static supported() {
    return typeof navigator !== "undefined" && "serial" in navigator;
  }

  async connect() {
    if (!BoardLink.supported()) throw new Error("This browser has no Web Serial. Use Chrome or Edge on a computer.");
    this.port = await navigator.serial.requestPort();
    await this.port.open({ baudRate: this.baud });
    this.onStatus("Connected. Waiting for samples…");
    this.reading = true;
    this._readLoop();
  }

  async disconnect() {
    this.reading = false;
    try {
      if (this.reader) await this.reader.cancel();
      if (this.port) await this.port.close();
    } catch (error) {
      // The port may already be gone (unplugged); there's nothing more to close.
    }
    this.onStatus("Disconnected.");
  }

  async _readLoop() {
    const decoder = new TextDecoderStream();
    this.port.readable.pipeTo(decoder.writable).catch(() => {});
    this.reader = decoder.readable.getReader();
    let buffer = "";
    while (this.reading) {
      const { value, done } = await this.reader.read();
      if (done) break;
      buffer += value;
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop();
      for (const line of lines) {
        const sample = parseLine(line, this.vref, this.bits);
        if (sample) this.onSample(sample);
      }
    }
  }
}

export function parseLine(line, vref = 5.0, bits = 10) {
  // "1234,512,0,1023,77" -> {t: 1.234, volts: [2.5, 0, 5, 0.376]}; anything else (like a startup
  // banner starting with '#') is ignored.
  if (!line || line.startsWith("#")) return null;
  const fields = line.split(",").map(Number);
  if (fields.length < 2 || fields.some((v) => !Number.isFinite(v))) return null;
  const full = Math.pow(2, bits) - 1;
  return { t: fields[0] / 1000, volts: fields.slice(1).map((counts) => (counts / full) * vref) };
}
