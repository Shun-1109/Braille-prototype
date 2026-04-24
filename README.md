Braille Reader Prototype
A prototype assistive device for blind users that captures printed text and outputs it as Braille patterns via solenoids.
System Overview

Raspberry Pi 4 captures JPEG frames using the Camera Module
Frames are sent to a Flask server (laptop/PC)
The server collects frames over a time window
The server selects the best frame (sharpness, contrast, brightness scoring)
The server preprocesses the image (CLAHE, sharpening, adaptive thresholding, deskew)
EasyOCR extracts the text
ESP32-C3 polls the server for the latest recognized text
ESP32 drives 6 solenoids to output Braille patterns one character at a time

Hardware
ComponentDetailsRaspberry Pi 4Main capture deviceRaspberry Pi Camera ModuleImage captureLaptop / PCRuns Flask serverESP32-C3 Super MiniBraille output controller6 × 3 V solenoidsBraille cell actuatorsLogic-level MOSFETsSolenoid driversFlyback diodesSolenoid protectionDC-DC convertersPower regulationBattery packPortable power
Braille Cell Layout
[1] [2]
[3] [4]
[5] [6]

Software Components
FileDescriptionRPI.pyRaspberry Pi camera client — captures and uploads JPEG framesServer.pyFlask server — frame selection, preprocessing, OCR, REST APIESP-supermini-braille.ino ESP32-C3 sketch — Wi-Fi client, Braille conversion, solenoid control

Dependencies
Raspberry Pi
picamera2
requests
Server
flask
opencv-python
easyocr
numpy
ESP32

Arduino IDE with ESP32 board support
WiFi.h, HTTPClient.h (bundled with ESP32 Arduino core)

Setup & Usage

1. Configure the server
Edit Server.py and set:
pythonSERVER_IP   = "YOUR_SERVER_IP"
SERVER_PORT = 5000
BASE_DIR    = "/path/to/output/folder"
Start the server:
bashpython Server.py

2. Configure and start the Raspberry Pi client
Edit RPI.py and set:
pythonSERVER_URL = "http://YOUR_SERVER_IP:5000/upload"
Run on the Raspberry Pi:
bashpython RPI.py

3. Flash the ESP32
Open ESP-supermini-braille.ino in the Arduino IDE and set:
cppconst char* ssid     = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* serverIP = "YOUR_SERVER_IP";
Flash to the ESP32-C3 Super Mini.

4. Test
Once the Raspberry Pi is streaming and OCR text is available, the ESP32 will fetch it and output Braille patterns through the solenoids.
Server API Endpoints
EndpointMethodDescription/uploadPOSTReceive JPEG frame from Raspberry Pi/text_onlyGETReturn latest OCR text as plain string/resultGETReturn full result JSON (text, file, batch_id, timestamp)/statusGETReturn collection/processing status
License
MIT
