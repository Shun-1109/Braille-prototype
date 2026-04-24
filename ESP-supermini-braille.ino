#include <WiFi.h>
#include <HTTPClient.h>
#include <ctype.h>

const char* ssid     = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* serverIP = "YOUR_SERVER_IP";

const int SOLENOID_PINS[6] = {0, 1, 3, 4, 5, 6};
const bool ACTIVE_HIGH = true;

const unsigned long START_DELAY_AFTER_TEXT_MS = 3000;
const unsigned long LETTER_INTERVAL_MS = 1000;
const unsigned long WORD_END_DELAY_MS = 1500;

const int BRAILLE_TO_PHYSICAL[6] = {
  0,
  2,
  4,
  1,
  3,
  5
};

#define BRAILLE(d1, d2, d3, d4, d5, d6) \
  ((d1 ? 1 : 0) | (d2 ? 2 : 0) | (d3 ? 4 : 0) | (d4 ? 8 : 0) | (d5 ? 16 : 0) | (d6 ? 32 : 0))

void writeSolenoidPhysical(int physicalIndex, bool on) {
  bool level = ACTIVE_HIGH ? on : !on;
  digitalWrite(SOLENOID_PINS[physicalIndex], level ? HIGH : LOW);
}

void clearAllSolenoids() {
  for (int i = 0; i < 6; i++) {
    writeSolenoidPhysical(i, false);
  }
}

uint8_t charToBraille(char c) {
  c = tolower((unsigned char)c);

  switch (c) {
    case 'a': return BRAILLE(1,0,0,0,0,0);
    case 'b': return BRAILLE(1,1,0,0,0,0);
    case 'c': return BRAILLE(1,0,0,1,0,0);
    case 'd': return BRAILLE(1,0,0,1,1,0);
    case 'e': return BRAILLE(1,0,0,0,1,0);
    case 'f': return BRAILLE(1,1,0,1,0,0);
    case 'g': return BRAILLE(1,1,0,1,1,0);
    case 'h': return BRAILLE(1,1,0,0,1,0);
    case 'i': return BRAILLE(0,1,0,1,0,0);
    case 'j': return BRAILLE(0,1,0,1,1,0);

    case 'k': return BRAILLE(1,0,1,0,0,0);
    case 'l': return BRAILLE(1,1,1,0,0,0);
    case 'm': return BRAILLE(1,0,1,1,0,0);
    case 'n': return BRAILLE(1,0,1,1,1,0);
    case 'o': return BRAILLE(1,0,1,0,1,0);
    case 'p': return BRAILLE(1,1,1,1,0,0);
    case 'q': return BRAILLE(1,1,1,1,1,0);
    case 'r': return BRAILLE(1,1,1,0,1,0);
    case 's': return BRAILLE(0,1,1,1,0,0);
    case 't': return BRAILLE(0,1,1,1,1,0);

    case 'u': return BRAILLE(1,0,1,0,0,1);
    case 'v': return BRAILLE(1,1,1,0,0,1);
    case 'w': return BRAILLE(0,1,0,1,1,1);
    case 'x': return BRAILLE(1,0,1,1,0,1);
    case 'y': return BRAILLE(1,0,1,1,1,1);
    case 'z': return BRAILLE(1,0,1,0,1,1);

    case '1': return BRAILLE(1,0,0,0,0,0);
    case '2': return BRAILLE(1,1,0,0,0,0);
    case '3': return BRAILLE(1,0,0,1,0,0);
    case '4': return BRAILLE(1,0,0,1,1,0);
    case '5': return BRAILLE(1,0,0,0,1,0);
    case '6': return BRAILLE(1,1,0,1,0,0);
    case '7': return BRAILLE(1,1,0,1,1,0);
    case '8': return BRAILLE(1,1,0,0,1,0);
    case '9': return BRAILLE(0,1,0,1,0,0);
    case '0': return BRAILLE(0,1,0,1,1,0);

    case ' ':
    case '\n':
    case '\r':
      return 0;

    default:
      return 0;
  }
}

void showBrailleMask(uint8_t mask) {
  for (int logicalDot = 0; logicalDot < 6; logicalDot++) {
    bool enabled = (mask & (1 << logicalDot)) != 0;
    int physicalIndex = BRAILLE_TO_PHYSICAL[logicalDot];
    writeSolenoidPhysical(physicalIndex, enabled);
  }
}

void showCharacter(char c) {
  if (c == ' ' || c == '\n' || c == '\r') {
    delay(LETTER_INTERVAL_MS);
    return;
  }

  uint8_t mask = charToBraille(c);

  Serial.print("Character: ");
  Serial.print(c);
  Serial.print(" -> mask: ");
  Serial.println(mask);

  showBrailleMask(mask);
  delay(LETTER_INTERVAL_MS);
}

void showText(const String& text) {
  for (size_t i = 0; i < text.length(); i++) {
    showCharacter(text[i]);
  }

  delay(WORD_END_DELAY_MS);
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Wi-Fi connected");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
}

String fetchTextFromServer() {
  HTTPClient http;
  http.begin(TEXT_URL);

  int httpCode = http.GET();
  if (httpCode != HTTP_CODE_OK) {
    Serial.print("HTTP GET failed: ");
    Serial.println(httpCode);
    http.end();
    return "";
  }

  String payload = http.getString();
  http.end();

  payload.trim();
  return payload;
}

void setup() {
  Serial.begin(115200);

  for (int i = 0; i < 6; i++) {
    pinMode(SOLENOID_PINS[i], OUTPUT);
  }
  clearAllSolenoids();

  connectWiFi();

  Serial.println("Requesting text from server...");
  String text = fetchTextFromServer();

  if (text.length() == 0) {
    Serial.println("No text received.");
    return;
  }

  Serial.println("Text received:");
  Serial.println(text);

  Serial.print("Waiting ");
  Serial.print(START_DELAY_AFTER_TEXT_MS);
  Serial.println(" ms before starting solenoids...");
  delay(START_DELAY_AFTER_TEXT_MS);

  showText(text);
}

void loop() {
}
