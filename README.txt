# Braille Reader Prototype

This project is a prototype of an assistive device for blind users.

The system captures printed text with a Raspberry Pi camera, sends image frames to a laptop server, selects the best frame, preprocesses it, runs OCR, and sends the recognized text to an ESP32-C3 device. The ESP32 then drives 6 solenoids as a single Braille cell.

## System Overview

Project flow:

1. Raspberry Pi 4 captures JPEG frames using the Raspberry Pi Camera Module
2. Frames are sent to the laptop Flask server
3. The server collects frames for a time window
4. The server selects the best frame
5. The server preprocesses the image for OCR
6. OCR extracts the text
7. ESP32-C3 requests the text from the server
8. ESP32 outputs Braille patterns using 6 solenoids

## Hardware

- Raspberry Pi 4
- Raspberry Pi Camera Module
- Windows laptop running Flask server
- ESP32-C3 Super Mini
- 6 x 3V solenoids
- Logic-level MOSFETs
- Flyback diodes
- DC-DC converters
- Battery pack

## Software Components

### Raspberry Pi
- `raspberry_pi/rpi_camera.py`
- Captures images using `picamera2`
- Sends JPEG frames to the server

### Server
- `server/server.py`
- Flask server
- Receives images
- Selects best frame
- Preprocesses image
- Runs OCR
- Exposes `/text_only`, `/result`, `/status`

### ESP32
- `esp32/braille_client.ino`
- Connects to Wi-Fi
- Requests text from the server
- Converts text to Braille
- Drives 6 solenoids

## Braille Cell Layout

Physical prototype layout currently used:

```text
[1] [2]
[3] [4]
[5] [6]


```How To Run
1. Start the Flask server
-Run the Python server on the laptop.

2. Start Raspberry Pi capture
-Run the Raspberry Pi camera client so it uploads images to the server.

3. Flash ESP32
-Upload the ESP32 sketch and configure:

	Wi-Fi SSID
	Wi-Fi password
	server IP address
4. Test the prototype
-Once OCR text is available, ESP32 fetches it and outputs Braille patterns.
