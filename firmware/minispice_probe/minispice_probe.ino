// MiniSpice probe: streams analog readings to MiniSpice over USB.
//
// Output, one line per sample at 115200 baud:
//     t_ms,a0,a1,a2,a3        (raw ADC counts)
// MiniSpice turns counts into volts with the board's reference voltage and resolution.
//
// It also drives a 50 Hz, 0-to-supply square wave on TEST_PIN, a ready-made input for the
// RC lab (examples/lab/lab_rc.cir).
//
// Serial commands (send a line):
//     r<hz>   sample rate, e.g. "r500" (default 1000 Hz on an Uno, ~4 channels)
//     f<hz>   test square wave frequency, e.g. "f100" (0 turns it off)
//
// SAFETY: analog inputs take 0 V to the board's supply ONLY (5 V on an Uno, 3.3 V on an ESP32).
// Higher voltages, or any negative voltage, can destroy the pin or the whole board. See README.md.

#if defined(ESP32)
const int CHANNELS[] = {34, 35, 32, 33};  // ADC1 pins (ADC2 can't be used while Wi-Fi is on)
const int TEST_PIN = 25;
const int ADC_BITS = 12;
const float VREF = 3.3;
#else
const int CHANNELS[] = {A0, A1, A2, A3};
const int TEST_PIN = 9;
const int ADC_BITS = 10;
const float VREF = 5.0;
#endif

const int CHANNEL_COUNT = 4;
unsigned long samplePeriodUs = 1000;  // 1 kHz
unsigned long nextSampleUs = 0;
unsigned long testHalfPeriodUs = 10000;  // 50 Hz square wave
unsigned long nextToggleUs = 0;
bool testLevel = false;
String command = "";

void setup() {
  Serial.begin(115200);
  pinMode(TEST_PIN, OUTPUT);
#if defined(ESP32)
  analogReadResolution(ADC_BITS);
  analogSetAttenuation(ADC_11db);  // full 0-3.3 V input range
#endif
  // Lines starting with '#' are ignored by MiniSpice, so this banner is safe to send.
  Serial.print("# MiniSpice probe ready: ");
  Serial.print(ADC_BITS);
  Serial.print("-bit ADC, ");
  Serial.print(VREF);
  Serial.println(" V reference");
  nextSampleUs = micros();
  nextToggleUs = micros();
}

void handleCommand(const String &line) {
  if (line.length() < 2) return;
  long value = line.substring(1).toInt();
  if (line[0] == 'r' && value > 0 && value <= 5000) {
    samplePeriodUs = 1000000UL / value;
    Serial.print("# sample rate ");
    Serial.println(value);
  } else if (line[0] == 'f') {
    testHalfPeriodUs = value > 0 ? 500000UL / value : 0;
    if (testHalfPeriodUs == 0) digitalWrite(TEST_PIN, LOW);
    Serial.print("# test wave ");
    Serial.println(value);
  }
}

void loop() {
  unsigned long now = micros();

  // The square wave runs on its own schedule so its edges stay evenly spaced.
  if (testHalfPeriodUs > 0 && (long)(now - nextToggleUs) >= 0) {
    testLevel = !testLevel;
    digitalWrite(TEST_PIN, testLevel ? HIGH : LOW);
    nextToggleUs += testHalfPeriodUs;
  }

  if ((long)(now - nextSampleUs) >= 0) {
    nextSampleUs += samplePeriodUs;
    Serial.print(millis());
    for (int k = 0; k < CHANNEL_COUNT; k++) {
      Serial.print(',');
      Serial.print(analogRead(CHANNELS[k]));
    }
    Serial.println();
  }

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      handleCommand(command);
      command = "";
    } else if (command.length() < 16) {
      command += c;
    }
  }
}
