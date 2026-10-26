# MiniSpice probe firmware

Turns an Arduino Uno/Nano or an ESP32 into a 4-channel voltage logger that MiniSpice can read,
so measured waveforms can be compared with simulated ones.

## Before you wire anything: what can damage the board

| | Arduino Uno / Nano | ESP32 |
|---|---|---|
| Safe input range on analog pins | 0 V to 5 V | 0 V to 3.3 V |
| ADC resolution | 10-bit (0 to 1023) | 12-bit (0 to 4095) |
| Max current from an output pin | 20 mA (40 mA absolute max) | 12 mA recommended |
| Channels used | A0, A1, A2, A3 | GPIO 34, 35, 32, 33 |
| Test square wave | pin 9 | GPIO 25 |

- **Never** put more than the board's supply voltage on an input, or any negative voltage. A 9 V
  battery straight into A0 can destroy the chip. Measure higher voltages through a resistor divider
  (for example 10k over 10k halves the voltage), and simulate the divider in MiniSpice first.
- The circuit's ground and the board's GND must be connected, or the readings are meaningless.
- Don't connect an output pin straight to 5 V, GND or another output: the short-circuit current
  can burn out the pin. Always go through a resistor (220 Ω or more) or into a high-impedance input.
- The ESP32 is a 3.3 V board. Its pins are not 5 V tolerant.
- Readings are only as good as the reference: the Uno's 5 V comes from USB and can be 4.8 to 5.1 V.
  Measure it with a multimeter and pass it with `--vref` for the best accuracy.

## Upload

1. Install the [Arduino IDE](https://www.arduino.cc/en/software). For an ESP32, also add the
   ESP32 boards package (Boards Manager, search "esp32").
2. Open `minispice_probe/minispice_probe.ino`, pick your board and port, and click Upload.
3. In the Serial Monitor at 115200 baud you should see lines like `1234,512,0,1023,77`.
   Close the Serial Monitor before using MiniSpice, because only one program can hold the port.

## Use with MiniSpice

```
pip install pyserial
python -m minispice measure --port COM3 --seconds 0.2 --out rc.csv          # Windows
python -m minispice measure --port /dev/ttyACM0 --seconds 0.2 --out rc.csv  # Mac / Linux
python -m minispice overlay examples/lab/lab_rc.cir rc.csv --probe "v(cap)" --channel a1
```

For an ESP32 add `--vref 3.3 --bits 12`.

In the browser app, open the Oscilloscope tab and click **Connect board** (Chrome or Edge on a
computer). A0 is drawn over channel 1, A1 over channel 2, and so on, as dashed traces.

## Line format

One sample per line: `t_ms,a0,a1,a2,a3` with raw ADC counts. Lines starting with `#` are
messages, not samples. Send `r500` to sample at 500 Hz, or `f100` to change the test square wave to 100 Hz.
