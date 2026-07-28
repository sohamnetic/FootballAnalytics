from ultralytics import YOLO
from pathlib import Path

# Path where we want the model to live
model_path = Path(r"D:\FootballAnalytics\models\yolo11n.pt")

print("Loading model...")

# If the model isn't present, Ultralytics downloads it automatically.
model = YOLO(str(model_path) if model_path.exists() else "yolo11n.pt")

# Save a copy into our models folder if needed.
if not model_path.exists():
    model.save(str(model_path))

print("Model loaded successfully!")
print(f"Model path: {model_path}")