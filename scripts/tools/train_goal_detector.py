"""
Fine-tune YOLO11n to find goals (posts + net) on frames labelled by
scripts/tools/label_goals.py, and install it as config.GOAL_MODEL.

Heavy colour/scale augmentation stands in for venue variety: goals look
alike everywhere (white frame, net), but backgrounds, lighting and camera
distance don't. Label more venues with label_goals.py into the same dataset
and re-run this to generalise further.

  python -m scripts.tools.train_goal_detector --data data/goal_dataset/data.yaml
"""
import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

from config.config import DEVICE, GOAL_IMGSZ, GOAL_MODEL, MODELS_DIR, PROJECT_ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(PROJECT_ROOT / "data" / "goal_dataset" / "data.yaml"))
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    model = YOLO(str(MODELS_DIR / "yolo11n.pt"))
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=GOAL_IMGSZ,
        batch=args.batch,
        workers=args.workers,
        device=DEVICE,
        project=str(PROJECT_ROOT / "outputs" / "goal_training"),
        name="goal",
        exist_ok=True,
        single_cls=True,
        patience=15,
        hsv_h=0.1, hsv_s=0.6, hsv_v=0.5,
        scale=0.6, translate=0.2, degrees=3.0, fliplr=0.5,
        mosaic=1.0, close_mosaic=10,
        plots=True,
        verbose=False,
    )
    best = Path(model.trainer.save_dir) / "weights" / "best.pt"
    metrics = YOLO(str(best)).val(
        data=args.data, imgsz=GOAL_IMGSZ, device=DEVICE, verbose=False,
        project=str(PROJECT_ROOT / "outputs" / "goal_training"), name="goal_val", exist_ok=True,
    )
    shutil.copy2(best, GOAL_MODEL)
    print(f"goal model -> {GOAL_MODEL}  (val mAP50 {metrics.box.map50:.3f}, mAP50-95 {metrics.box.map:.3f})")


if __name__ == "__main__":
    main()
