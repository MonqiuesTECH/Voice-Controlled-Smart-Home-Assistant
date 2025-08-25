/*
 * Simple Smart Home Arduino sketch.
 * Listens for newline-delimited commands over Serial from device_bridge.py.
 *
 * Protocol (one line per command):
 *   LIGHT:<location>:ON|OFF
 *   FAN:<location>:ON|OFF
 *   THERMOSTAT:<location>:<int_temp>
 *   GARAGE:<location>:OPEN|CLOSE
 */

#include <Servo.h>

const int PIN_LIGHT = 13;   // Onboard LED or external LED
const int PIN_FAN   = 7;    // Example relay pin
const int PIN_SERVO = 9;    // Garage servo

Servo garageServo;
String lineBuf;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LIGHT, OUTPUT);
  pinMode(PIN_FAN, OUTPUT);
  garageServo.attach(PIN_SERVO);
  garageServo.write(0); // closed
  Serial.println("[arduino] ready");
}

void setLight(bool on) { digitalWrite(PIN_LIGHT, on ? HIGH : LOW); }
void setFan(bool on)   { digitalWrite(PIN_FAN, on ? HIGH : LOW); }

void setGarage(const String &state) {
  if (state == "OPEN") {
    garageServo.write(90);
  } else {
    garageServo.write(0);
  }
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      lineBuf.trim();
      if (lineBuf.length() > 0) {
        // Parse: DEVICE:location:VALUE
        // We ignore 'location' on Arduino and just act globally,
        // but you can map locations to different pins if desired.
        int p1 = lineBuf.indexOf(':');
        int p2 = lineBuf.indexOf(':', p1 + 1);
        String dev = (p1 > 0) ? lineBuf.substring(0, p1) : "";
        String val = (p2 > p1) ? lineBuf.substring(p2 + 1) : "";

        if (dev == "LIGHT") {
          setLight(val == "ON");
          Serial.println("[arduino] LIGHT -> " + val);
        } else if (dev == "FAN") {
          setFan(val == "ON");
          Serial.println("[arduino] FAN -> " + val);
        } else if (dev == "GARAGE") {
          setGarage(val);
          Serial.println("[arduino] GARAGE -> " + val);
        } else if (dev == "THERMOSTAT") {
          // No real thermostat; just log
          Serial.println("[arduino] THERMOSTAT -> " + val + "°");
        } else {
          Serial.println("[arduino] UNKNOWN: " + lineBuf);
        }
      }
      lineBuf = "";
    } else {
      lineBuf += c;
    }
  }
}
