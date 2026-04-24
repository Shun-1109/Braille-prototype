import io
import time

import requests
from picamera2 import Picamera2

# ── Configuration ─────────────────────────────────────────────────────────────
SERVER_URL      = "http://YOUR_SERVER_IP:5000/upload"  # <- CHANGE THIS
INTERVAL_SECONDS = 0.2   # seconds between frames (200 ms)
JPEG_QUALITY     = 95    # JPEG encode quality (1-100)
REQUEST_TIMEOUT  = 5     # HTTP request timeout in seconds
IMAGE_SIZE       = (1920, 1080)  # capture resolution
# ──────────────────────────────────────────────────────────────────────────────

picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": IMAGE_SIZE})
picam2.configure(config)
picam2.options["quality"] = JPEG_QUALITY

print("Starting camera...")
picam2.start()

print("Warming up camera...")
time.sleep(2)

print(f"Sending frames every {INTERVAL_SECONDS}s to {SERVER_URL}")

try:
    while True:
        start_time = time.monotonic()

        stream = io.BytesIO()
        picam2.capture_file(stream, format="jpeg")
        image_bytes = stream.getvalue()

        try:
            response = requests.post(
                SERVER_URL,
                data=image_bytes,
                headers={"Content-Type": "image/jpeg"},
                timeout=REQUEST_TIMEOUT,
            )
            print(f"Sent: {response.status_code}")
        except requests.RequestException as exc:
            print(f"Send error: {exc}")

        elapsed    = time.monotonic() - start_time
        sleep_time = max(0, INTERVAL_SECONDS - elapsed)
        time.sleep(sleep_time)

except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    picam2.stop()
