"""Download the models into models/ (skips the ones you already have)."""
import urllib.request

from ultralytics import YOLO

from config.config import IDENTITY_REID_WEIGHTS, MODELS_DIR, PERSON_MODEL, YOLO_MODEL

REID_URL = "https://github.com/mikel-brostrom/boxmot/releases/download/v21.0.0/lmbn_n_duke.pt"

MODELS_DIR.mkdir(parents=True, exist_ok=True)

for path in (YOLO_MODEL, PERSON_MODEL):
    if path.exists():
        print(f"present   : {path}")
        continue
    # Ultralytics downloads official weights by bare name into the cwd.
    model = YOLO(path.name)
    model.save(str(path))
    print(f"downloaded: {path}")

if IDENTITY_REID_WEIGHTS.exists():
    print(f"present   : {IDENTITY_REID_WEIGHTS}")
else:
    urllib.request.urlretrieve(REID_URL, IDENTITY_REID_WEIGHTS)
    print(f"downloaded: {IDENTITY_REID_WEIGHTS}")

print("Jersey OCR (EasyOCR) weights download to ~/.EasyOCR on first use.")
