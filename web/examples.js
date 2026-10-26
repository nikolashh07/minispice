// Starter designs. Each is a netlist whose "* @part" and "* @wire" comments hold the drawing, so
// the editor loads them exactly as laid out here (the node numbers on the part lines get
// recomputed from the wires).

export const EXAMPLES = {
  "Voltage divider": `* Voltage divider
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
R1 1 2 1k
R2 2 0 1k
`,
  "RC low-pass filter": `* RC low-pass filter: probe node 2 and run the scope, or the Bode plotter with V1
* @part V1 V 4 8 0
* @part R1 R 8 4 0
* @part C1 C 12 8 90
* @part GND1 GND 8 12 0
* @wire 4 6 4 4
* @wire 4 4 6 4
* @wire 10 4 12 4
* @wire 12 4 12 6
* @wire 4 10 4 12
* @wire 4 12 12 12
* @wire 12 12 12 10
V1 1 0 PULSE(0 5 0 1u 1u 2m 4m)
R1 1 2 1k
C1 2 0 1u
`,
  "LED and resistor": `* Red LED with a current-limiting resistor
* @part V1 V 4 8 0
* @part R1 R 8 4 0
* @part D1 LED 12 8 90
* @part GND1 GND 8 12 0
* @wire 4 6 4 4
* @wire 4 4 6 4
* @wire 10 4 12 4
* @wire 12 4 12 6
* @wire 4 10 4 12
* @wire 4 12 12 12
* @wire 12 12 12 10
V1 1 0 5
R1 1 2 330 rating=0.25
D1 2 0 led_red
`,
  "Inverting amplifier": `* Inverting amplifier, gain -RF/RIN = -10
* @part VIN V 4 10 0
* @part RIN R 8 6 0
* @part RF R 14 2 0
* @part U1 OPAMP 16 8 0
* @part RL R 20 12 90
* @part GND1 GND 4 14 0
* @part GND2 GND 14 12 0
* @part GND3 GND 20 16 0
* @wire 4 8 4 6
* @wire 4 6 6 6
* @wire 10 6 12 6
* @wire 12 6 12 7
* @wire 12 7 14 7
* @wire 12 2 12 6
* @wire 16 2 20 2
* @wire 20 2 20 8
* @wire 18 8 20 8
* @wire 20 8 20 10
* @wire 14 9 14 12
* @wire 4 12 4 14
* @wire 20 14 20 16
VIN 1 0 SIN(0 0.5 1k)
RIN 1 2 1k
RF 2 3 10k
U1 0 2 3
RL 3 0 10k
`,
  "CMOS inverter": `* CMOS inverter switching a small load capacitor
* @part VIN V 4 9 0
* @part M2 PMOS 12 4 0
* @part M1 NMOS 12 10 0
* @part CL C 17 9 90
* @part VDD V 22 6 0
* @part GND1 GND 4 13 0
* @part GND2 GND 13 14 0
* @part GND3 GND 17 13 0
* @part GND4 GND 22 10 0
* @wire 13 6 13 8
* @wire 13 7 17 7
* @wire 10 4 8 4
* @wire 8 4 8 10
* @wire 8 10 10 10
* @wire 4 7 8 7
* @wire 4 11 4 13
* @wire 13 12 13 14
* @wire 17 11 17 13
* @wire 13 2 22 2
* @wire 22 2 22 4
* @wire 22 8 22 10
VIN 1 0 PULSE(0 5 0 10u 10u 0.5m 1m)
M2 2 1 3 pmos
M1 2 1 0 nmos
CL 2 0 1n
VDD 3 0 5
`,
};
