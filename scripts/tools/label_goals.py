"""
Make training data for the goal detector from a match video.

Grounding DINO finds goal-like boxes every --every-s seconds. It also
boxes a lot of other stuff (penalty areas, doors, walls, the crowd), so a
box is only kept if:
- it's not too big
- CLIP agrees it looks like a goal
- there's turf right under it
- it's not just a bigger box around another goal box
- we find the same box again in nearby frames (goals don't move)

Frames with nothing goal-like are saved as "no goal" examples. Anything
unclear is skipped. Check the labels by eye before training and pass bad
frames with --drop-frames.

Needs `pip install transformers` (only for this tool).

  python -m scripts.tools.label_goals --video path/to/match.mp4 \
      --out data/goal_dataset --name match5min
"""
import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from scripts.vision.camera_motion import CameraMotion
from scripts.vision.turf import turf_mask

PROMPT = "a soccer goal with white goalposts and net."
PROPOSAL_MIN_SCORE = 0.15
MAX_W, MAX_H = 0.25, 0.70        # of frame size
MIN_SIDE_PX = 20
STRONG, WEAK = 0.35, 0.20        # proposal scores
CLIP_MODEL = "openai/clip-vit-large-patch14"
CLIP_TEXTS = [
    "a soccer goal with white posts and a net", "a door", "a wall", "a window",
    "people sitting in the stands", "a grass field with white lines", "a large screen",
    "a banner", "a fence net", "a person",
]
CLIP_GOAL, CLIP_GOAL_WITH_STRONG_BOX, BOX_STRONG_FOR_CLIP = 0.6, 0.3, 0.45
MIN_TURF_BELOW = 0.3
CONFIRM_WINDOW_S = 3.0
CONFIRM_IOU = 0.4
NEGATIVE_WINDOW_S = 1.0


def _map_box(box, t):
    """Apply a camera transform to a box."""
    x1, y1, x2, y2 = box
    pts = np.array([[x1, y1, 1], [x2, y1, 1], [x1, y2, 1], [x2, y2, 1]], float) @ t.T
    return [pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()]


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _goal_like(box, width, height):
    w, h = box[2] - box[0], box[3] - box[1]
    return MIN_SIDE_PX <= w <= MAX_W * width and MIN_SIDE_PX <= h <= MAX_H * height


def propose(video, every_s, model_name, image_dir, name, start_s=0.0, duration_s=None):
    import torch
    from PIL import Image
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    proc = AutoProcessor.from_pretrained(model_name)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_name).to(device).eval()

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    first = int(start_s * fps)
    last = first + int(duration_s * fps) if duration_s else None
    step = max(1, int(round(every_s * fps)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)

    camera = CameraMotion()
    samples = []
    frame_no = first
    image_dir.mkdir(parents=True, exist_ok=True)
    while last is None or frame_no < last:
        ok, frame = cap.read()
        if not ok:
            break
        transform = camera.update(frame, [])
        if (frame_no - first) % step == 0:
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            inputs = proc(images=img, text=PROMPT, return_tensors="pt").to(device)
            with torch.no_grad():
                out = model(**inputs)
            det = proc.post_process_grounded_object_detection(
                out, inputs.input_ids, threshold=PROPOSAL_MIN_SCORE, text_threshold=PROPOSAL_MIN_SCORE,
                target_sizes=[(height, width)],
            )[0]
            path = image_dir / f"{name}_{frame_no:06d}.jpg"
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            samples.append({
                "frame": frame_no,
                "image": str(path),
                "transform": transform.tolist(),
                "boxes": [[*map(float, b), float(s)] for b, s in
                          zip(det["boxes"].cpu().numpy(), det["scores"].cpu().numpy())],
            })
            if len(samples) % 50 == 0:
                print(f"  {len(samples)} frames proposed (frame {frame_no})", flush=True)
        frame_no += 1
    cap.release()
    return {"fps": fps, "width": width, "height": height, "samples": samples}


def _turf_below(img, box):
    """How much turf is right below the box."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    bh, bw = y2 - y1, x2 - x1
    strip = img[int(max(0, y2 - 0.03 * bh)):int(min(h, y2 + 0.12 * bh)),
                int(max(0, x1 + 0.2 * bw)):int(min(w, x2 - 0.2 * bw))]
    if strip.size == 0:
        return 1.0  # bottom is outside the frame, don't reject it
    return float(turf_mask(cv2.cvtColor(strip, cv2.COLOR_BGR2HSV).reshape(-1, 3)).mean())


def verify(proposals, device=None):
    """Add the CLIP goal score (box[5]) and turf below (box[6]) to each box."""
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor

    width, height = proposals["width"], proposals["height"]
    todo = [(s, b) for s in proposals["samples"] for b in s["boxes"]
            if len(b) < 7 and _goal_like(b[:4], width, height)]
    if not todo:
        return proposals
    model = proc = None
    images = {}
    for s, b in todo:
        img = images.get(s["image"])
        if img is None:
            images.clear()
            img = images[s["image"]] = cv2.imread(s["image"])
        if len(b) == 5:
            if model is None:
                device = device or ("cuda" if torch.cuda.is_available() else "cpu")
                model = CLIPModel.from_pretrained(CLIP_MODEL).to(device).eval()
                proc = CLIPProcessor.from_pretrained(CLIP_MODEL)
            x1, y1, x2, y2 = b[:4]
            mx, my = 0.15 * (x2 - x1), 0.15 * (y2 - y1)
            crop = img[int(max(0, y1 - my)):int(min(height, y2 + my)), int(max(0, x1 - mx)):int(min(width, x2 + mx))]
            inputs = proc(text=CLIP_TEXTS, images=Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)),
                          return_tensors="pt", padding=True).to(device)
            with torch.no_grad():
                b.append(float(model(**inputs).logits_per_image.softmax(-1)[0, 0]))
        b.append(_turf_below(img, b[:4]))
    return proposals


def _looks_like_goal(box):
    p_goal = box[5] if len(box) > 5 else 0.0
    turf = box[6] if len(box) > 6 else 0.0
    clip_ok = p_goal >= CLIP_GOAL or (p_goal >= CLIP_GOAL_WITH_STRONG_BOX and box[4] >= BOX_STRONG_FOR_CLIP)
    return clip_ok and turf >= MIN_TURF_BELOW


def _contains(outer, inner):
    ix = max(0.0, min(outer[2], inner[2]) - max(outer[0], inner[0]))
    iy = max(0.0, min(outer[3], inner[3]) - max(outer[1], inner[1]))
    area_in = (inner[2] - inner[0]) * (inner[3] - inner[1])
    area_out = (outer[2] - outer[0]) * (outer[3] - outer[1])
    return area_in > 0 and ix * iy >= 0.8 * area_in and area_in <= 0.6 * area_out


def decide(proposals):
    """Decide for each frame: goal, background or skip."""
    fps, width, height = proposals["fps"], proposals["width"], proposals["height"]
    samples = proposals["samples"]
    for s in samples:
        t = np.array(s["transform"])
        s["cands"] = [
            {"box": b[:4], "score": b[4], "stab": _map_box(b[:4], t), "goal": _looks_like_goal(b)}
            for b in s["boxes"] if _goal_like(b[:4], width, height)
        ]
        # drop boxes that contain a smaller goal box
        for c in s["cands"]:
            if c["goal"] and any(o is not c and o["goal"] and _contains(c["box"], o["box"]) for o in s["cands"]):
                c["goal"] = False

    frames = np.array([s["frame"] for s in samples])
    for i, s in enumerate(samples):
        near = np.flatnonzero(np.abs(frames - s["frame"]) <= CONFIRM_WINDOW_S * fps)
        for c in s["cands"]:
            support = sum(
                any(_iou(c["stab"], o["stab"]) >= CONFIRM_IOU for o in samples[j]["cands"])
                for j in near if j != i
            )
            c["support"] = support
            c["accepted"] = c["goal"] and (
                (c["score"] >= STRONG and support >= 1) or (c["score"] >= WEAK and support >= 2)
            )

    for i, s in enumerate(samples):
        boxes = sorted((c for c in s["cands"] if c["accepted"]), key=lambda c: -c["score"])
        keep = []
        for c in boxes:
            if all(_iou(c["box"], k["box"]) < 0.3 for k in keep):
                keep.append(c)
        if keep:
            s["label"] = "goal"
            s["goals"] = [k["box"] for k in keep]
            continue
        # only call it background if no goal should be visible here
        t_inv = np.linalg.inv(np.array(s["transform"]))
        near = np.flatnonzero(np.abs(frames - s["frame"]) <= NEGATIVE_WINDOW_S * fps)
        expected = False
        for j in near:
            for c in samples[j]["cands"]:
                if c.get("accepted"):
                    x1, y1, x2, y2 = _map_box(c["stab"], t_inv)
                    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                    expected |= 0 <= cx < width and 0 <= cy < height

        doubtful = any(c["goal"] or c["score"] >= STRONG for c in s["cands"])
        s["label"] = "skip" if (doubtful or expected) else "background"
        s["goals"] = []
    return samples


def write_dataset(samples, width, height, out, val_every_s, fps):
    """Write images + labels in YOLO format. Every 5th 30s block goes to val."""
    counts = {"goal": 0, "background": 0, "skip": 0}
    for s in samples:
        counts[s["label"]] += 1
        src = Path(s["image"])
        if s["label"] == "skip":
            continue
        split = "val" if int(s["frame"] / (val_every_s * fps)) % 5 == 4 else "train"
        img_dir, lbl_dir = out / "images" / split, out / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, img_dir / src.name)
        lines = []
        for x1, y1, x2, y2 in s["goals"]:
            x1, x2 = max(0.0, x1), min(float(width), x2)
            y1, y2 = max(0.0, y1), min(float(height), y2)
            lines.append(f"0 {(x1 + x2) / 2 / width:.6f} {(y1 + y2) / 2 / height:.6f} "
                         f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}")
        (lbl_dir / f"{src.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
    (out / "data.yaml").write_text(
        f"path: {out.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: goal\n",
        encoding="utf-8",
    )
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="data/goal_dataset")
    ap.add_argument("--name", required=True, help="prefix for this video's images")
    ap.add_argument("--every-s", type=float, default=0.5)
    ap.add_argument("--start-s", type=float, default=0.0)
    ap.add_argument("--duration-s", type=float, default=None)
    ap.add_argument("--model", default="IDEA-Research/grounding-dino-base")
    ap.add_argument("--drop-frames", default="",
                    help="comma-separated frames a human review found wrong; saved to <name>_dropped.txt")
    args = ap.parse_args()

    out = Path(args.out)
    cache = out / "_proposals"
    prop_path = cache / f"{args.name}.json"
    if prop_path.exists():
        proposals = json.loads(prop_path.read_text(encoding="utf-8"))
    else:
        proposals = propose(args.video, args.every_s, args.model, cache / "images", args.name,
                            args.start_s, args.duration_s)
        prop_path.write_text(json.dumps(proposals), encoding="utf-8")
    if any(len(b) < 7 and _goal_like(b[:4], proposals["width"], proposals["height"])
           for smp in proposals["samples"] for b in smp["boxes"]):
        proposals = verify(proposals)
        prop_path.write_text(json.dumps(proposals), encoding="utf-8")
    samples = decide(proposals)
    dropped_path = cache / f"{args.name}_dropped.txt"
    if args.drop_frames:
        dropped_path.write_text(args.drop_frames.replace(",", " "), encoding="utf-8")
    dropped = {int(f) for f in dropped_path.read_text(encoding="utf-8").split()} if dropped_path.exists() else set()
    for smp in samples:
        if smp["frame"] in dropped:
            smp["label"], smp["goals"] = "skip", []
    counts = write_dataset(samples, proposals["width"], proposals["height"], out, 30.0, proposals["fps"])
    (cache / f"{args.name}_labels.json").write_text(json.dumps(
        [{k: s[k] for k in ("frame", "image", "label", "goals")} for s in samples]), encoding="utf-8")
    print(f"{args.name}: {counts}")


if __name__ == "__main__":
    main()
