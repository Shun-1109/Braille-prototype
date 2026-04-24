import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import cv2
import easyocr
import numpy as np
from flask import Flask, jsonify, request

# ── Configuration ─────────────────────────────────────────────────────────────
SERVER_IP   = "YOUR_SERVER_IP"   # <- CHANGE THIS
SERVER_PORT = 5000               # <- CHANGE THIS

BASE_DIR         = "/path/to/output/folder"              # <- CHANGE THIS
IMAGES_DIR       = os.path.join(BASE_DIR, "images")
PREPROCESSED_DIR = os.path.join(BASE_DIR, "preprocessed")
RESULTS_DIR      = os.path.join(BASE_DIR, "results")

COLLECTION_WINDOW_SECONDS = 45   # <- CHANGE THIS
OCR_LANGUAGES = ["en"]           # <- CHANGE THIS  e.g. ["en", "ru"]
# ──────────────────────────────────────────────────────────────────────────────

RESULT_FILE = os.path.join(RESULTS_DIR, "latest.json")

for folder in (BASE_DIR, IMAGES_DIR, PREPROCESSED_DIR, RESULTS_DIR):
    os.makedirs(folder, exist_ok=True)

app = Flask(__name__)

# Initialize EasyOCR once at startup.
OCR_READER = easyocr.Reader(OCR_LANGUAGES, gpu=False)

state_lock    = threading.Lock()
pipeline_lock = threading.Lock()

collection_files:      List[str]            = []
collection_started_at: Optional[datetime]   = None
collection_deadline:   Optional[datetime]   = None
collection_timer:      Optional[threading.Timer] = None
current_batch_id = 0

latest_result_data: Dict[str, object] = {
    "text":         "",
    "file":         "",
    "batch_id":     0,
    "processed_at": None,
}


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def save_latest_result(data: Dict[str, object]) -> None:
    with open(RESULT_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


save_latest_result(latest_result_data)


# ── Image utilities ───────────────────────────────────────────────────────────

def order_points(points: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    sums  = points.sum(axis=1)
    rect[0] = points[np.argmin(sums)]
    rect[2] = points[np.argmax(sums)]
    diffs    = np.diff(points, axis=1)
    rect[1]  = points[np.argmin(diffs)]
    rect[3]  = points[np.argmax(diffs)]
    return rect


def resize_for_analysis(image: np.ndarray, max_side: int = 1600) -> np.ndarray:
    height, width = image.shape[:2]
    longest_side  = max(height, width)
    if longest_side <= max_side:
        return image
    scale = max_side / float(longest_side)
    return cv2.resize(
        image,
        (int(width * scale), int(height * scale)),
        interpolation=cv2.INTER_AREA,
    )


def detect_and_warp_document(image: np.ndarray) -> Tuple[np.ndarray, bool]:
    preview = resize_for_analysis(image)
    gray    = cv2.cvtColor(preview, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges   = cv2.Canny(blurred, 50, 150)
    edges   = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours     = sorted(contours, key=cv2.contourArea, reverse=True)

    scale_x = image.shape[1] / float(preview.shape[1])
    scale_y = image.shape[0] / float(preview.shape[0])

    for contour in contours[:20]:
        if cv2.contourArea(contour) < 0.10 * preview.shape[0] * preview.shape[1]:
            continue

        perimeter = cv2.arcLength(contour, True)
        approx    = cv2.approxPolyDP(contour, 0.02 * perimeter, True)

        if len(approx) != 4:
            continue

        points       = approx.reshape(4, 2).astype("float32")
        points[:, 0] *= scale_x
        points[:, 1] *= scale_y

        rect = order_points(points)
        top_left, top_right, bottom_right, bottom_left = rect

        max_width = int(max(
            np.linalg.norm(bottom_right - bottom_left),
            np.linalg.norm(top_right    - top_left),
        ))
        max_height = int(max(
            np.linalg.norm(top_right   - bottom_right),
            np.linalg.norm(top_left    - bottom_left),
        ))

        if max_width < 200 or max_height < 200:
            continue

        destination = np.array(
            [[0, 0], [max_width - 1, 0],
             [max_width - 1, max_height - 1], [0, max_height - 1]],
            dtype="float32",
        )
        matrix  = cv2.getPerspectiveTransform(rect, destination)
        warped  = cv2.warpPerspective(image, matrix, (max_width, max_height))
        return warped, True

    return image.copy(), False


def rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def estimate_skew_angle(binary_image: np.ndarray) -> float:
    foreground = np.column_stack(np.where(binary_image < 245))
    if len(foreground) < 100:
        return 0.0
    coords = foreground[:, ::-1].astype(np.float32)
    angle  = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle = angle - 90
    if abs(angle) > 15:
        return 0.0
    return float(angle)


def score_frame(image: np.ndarray) -> Tuple[float, Dict[str, float]]:
    warped, document_found = detect_and_warp_document(image)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast_std  = float(np.std(gray))

    edges      = cv2.Canny(gray, 75, 180)
    edge_ratio = float(np.count_nonzero(edges) / edges.size)

    brightness         = float(np.mean(gray))
    brightness_penalty = abs(brightness - 185.0) / 185.0

    score = (
        laplacian_var * 0.55
        + contrast_std  * 2.5
        + edge_ratio    * 2500.0
        - brightness_penalty * 30.0
        + (45.0 if document_found else 0.0)
    )

    metrics = {
        "laplacian_var":   round(laplacian_var, 3),
        "contrast_std":    round(contrast_std, 3),
        "edge_ratio":      round(edge_ratio, 6),
        "brightness":      round(brightness, 3),
        "document_found":  float(document_found),
    }
    return float(score), metrics


def preprocess_frame(image: np.ndarray) -> np.ndarray:
    warped, _ = detect_and_warp_document(image)
    gray      = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    clahe     = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    enhanced  = clahe.apply(gray)

    blurred   = cv2.GaussianBlur(enhanced, (0, 0), 3)
    sharpened = cv2.addWeighted(enhanced, 1.6, blurred, -0.6, 0)

    binary = cv2.adaptiveThreshold(
        sharpened, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 15,
    )
    binary = cv2.medianBlur(binary, 3)
    binary = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN,
        np.ones((2, 2), np.uint8), iterations=1,
    )

    angle = estimate_skew_angle(binary)
    if abs(angle) > 0.1:
        binary = rotate_image(binary, angle)

    return binary


# ── Pipeline ──────────────────────────────────────────────────────────────────

def pick_best_frame(file_list: List[str]) -> Tuple[Optional[str], Optional[float]]:
    best_path:  Optional[str]   = None
    best_score: Optional[float] = None

    for path in file_list:
        image = cv2.imread(path)
        if image is None:
            continue
        score, metrics = score_frame(image)
        log(f"Scored {os.path.basename(path)} -> {score:.3f} {metrics}")
        if best_score is None or score > best_score:
            best_score = score
            best_path  = path

    return best_path, best_score


def start_collection_window_locked() -> None:
    global collection_started_at, collection_deadline, collection_timer, current_batch_id

    current_batch_id     += 1
    collection_started_at = datetime.now()
    collection_deadline   = collection_started_at + timedelta(seconds=COLLECTION_WINDOW_SECONDS)

    if collection_timer is not None:
        collection_timer.cancel()

    collection_timer = threading.Timer(
        COLLECTION_WINDOW_SECONDS,
        finalize_collection_window,
        args=(current_batch_id,),
    )
    collection_timer.daemon = True
    collection_timer.start()

    log(
        f"Started batch {current_batch_id} "
        f"until {collection_deadline.strftime('%Y-%m-%d %H:%M:%S')}"
    )


def finalize_collection_window(batch_id: int) -> None:
    global collection_files, collection_started_at, collection_deadline, collection_timer

    with state_lock:
        if collection_started_at is None or batch_id != current_batch_id:
            return

        batch_files = list(collection_files)

        collection_files      = []
        collection_started_at = None
        collection_deadline   = None
        collection_timer      = None

    if not batch_files:
        log(f"Batch {batch_id} ended with no files.")
        return

    threading.Thread(
        target=run_pipeline,
        args=(batch_id, batch_files),
        daemon=True,
    ).start()


def run_pipeline(batch_id: int, file_list: List[str]) -> None:
    global latest_result_data

    with pipeline_lock:
        log(f"Running pipeline for batch {batch_id} with {len(file_list)} images.")

        try:
            best_path, best_score = pick_best_frame(file_list)
            if best_path is None:
                raise RuntimeError("No valid images found in batch.")

            original = cv2.imread(best_path)
            if original is None:
                raise RuntimeError(f"Failed to read best frame: {best_path}")

            preprocessed = preprocess_frame(original)

            preprocessed_filename = f"batch_{batch_id}_preprocessed.png"
            preprocessed_path     = os.path.join(PREPROCESSED_DIR, preprocessed_filename)
            cv2.imwrite(preprocessed_path, preprocessed)

            ocr_lines = OCR_READER.readtext(preprocessed, detail=0, paragraph=True)
            text      = "\n".join(line.strip() for line in ocr_lines if line.strip()).strip()

            result = {
                "text":         text,
                "file":         os.path.basename(best_path),
                "batch_id":     batch_id,
                "processed_at": datetime.now().isoformat(),
            }

            save_latest_result(result)

            with state_lock:
                latest_result_data = dict(result)

            score_text = f"{best_score:.3f}" if best_score is not None else "0.000"
            log(
                f"Batch {batch_id} finished. "
                f"Best={os.path.basename(best_path)} "
                f"Score={score_text} "
                f"TextLength={len(text)}"
            )

        except Exception as exc:
            log(f"Pipeline error for batch {batch_id}: {exc}")


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/upload", methods=["POST"])
def upload():
    image_bytes = request.data
    if not image_bytes:
        return "No JPEG data received", 400

    filename = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".jpg"
    filepath = os.path.join(IMAGES_DIR, filename)

    with open(filepath, "wb") as handle:
        handle.write(image_bytes)

    with state_lock:
        if collection_started_at is None:
            start_collection_window_locked()
        collection_files.append(filepath)
        queue_size = len(collection_files)

    log(f"Received {filename} | queue={queue_size}")
    return jsonify({"status": "ok", "file": filename, "queue_size": queue_size}), 200


@app.route("/result", methods=["GET"])
def result():
    with state_lock:
        return jsonify(dict(latest_result_data))


@app.route("/text_only", methods=["GET"])
def text_only():
    with state_lock:
        return latest_result_data.get("text", "")


@app.route("/status", methods=["GET"])
def status():
    with state_lock:
        started_at = collection_started_at.isoformat() if collection_started_at else None
        deadline   = collection_deadline.isoformat()   if collection_deadline   else None
        queue_size = len(collection_files)

        if collection_deadline is None:
            seconds_left = None
        else:
            seconds_left = max(0, int((collection_deadline - datetime.now()).total_seconds()))

    return jsonify({
        "collection_active":       started_at is not None,
        "collection_started_at":   started_at,
        "collection_deadline":     deadline,
        "collection_seconds_left": seconds_left,
        "queue_size":              queue_size,
        "processing_active":       pipeline_lock.locked(),
        "batch_id":                current_batch_id,
    })


if __name__ == "__main__":
    log(f"Server listening on http://{SERVER_IP}:{SERVER_PORT}")
    log(f"Images folder:      {IMAGES_DIR}")
    log(f"Preprocessed folder:{PREPROCESSED_DIR}")
    log(f"Result file:        {RESULT_FILE}")
    app.run(host="0.0.0.0", port=SERVER_PORT, debug=False)
