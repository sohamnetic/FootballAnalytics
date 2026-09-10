"""
Regenerate identity audit CSVs from a coordinate file (person rows only).
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from config.config import COORDINATE_OUTPUT, IDENTITY_OUTPUT, TEST_VIDEO

AUDIT_GAP = 180
CANDIDATE_DIST = 250
CURRENT_GAP = 150
CURRENT_DIST = 120
SHORT_FRAMES = 120
LONG_FRAMES = 1200


def run_audit(csv_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path)
    p = df[df["class"] == "person"].copy()
    p["stable_id"] = p["stable_id"].astype(int)
    p["track_id"] = p["track_id"].astype(int)

    p1 = (
        p.sort_values("confidence", ascending=False)
        .drop_duplicates(["stable_id", "frame"], keep="first")
        .sort_values(["stable_id", "frame"])
    )

    span_frames = int(p["frame"].max() - p["frame"].min() + 1)
    per_frame = p1.groupby("frame")["stable_id"].nunique()

    profiles = {}
    rows = []
    for sid, g in p1.groupby("stable_id"):
        tracks = sorted(g["track_id"].unique().tolist())
        first = int(g["frame"].min())
        last = int(g["frame"].max())
        n = int(len(g))
        first_row = g.iloc[0]
        last_row = g.iloc[-1]
        profiles[sid] = {
            "stable_id": sid,
            "frames": n,
            "first_frame": first,
            "last_frame": last,
            "duration_frames": last - first + 1,
            "track_id_count": len(tracks),
            "track_ids_seen": ";".join(str(t) for t in tracks),
            "last_x": float(last_row["center_x"]),
            "last_y": float(last_row["center_y"]),
            "first_x": float(first_row["center_x"]),
            "first_y": float(first_row["center_y"]),
        }
        rows.append({
            "stable_id": sid,
            "frames": n,
            "first_frame": first,
            "last_frame": last,
            "duration_frames": last - first + 1,
            "track_id_count": len(tracks),
            "track_ids_seen": ";".join(str(t) for t in tracks),
            "avg_x": round(float(g["center_x"].mean()), 2),
            "avg_y": round(float(g["center_y"].mean()), 2),
            "conf_mean": round(float(g["confidence"].mean()), 4),
        })

    audit = pd.DataFrame(rows).sort_values("stable_id")
    audit["longevity"] = "medium"
    audit.loc[audit["frames"] >= LONG_FRAMES, "longevity"] = "long"
    audit.loc[audit["frames"] <= SHORT_FRAMES, "longevity"] = "short"
    audit.to_csv(out_dir / "identity_audit.csv", index=False)

    ids = list(profiles.values())
    candidates = []
    for a in ids:
        for b in ids:
            if a["stable_id"] == b["stable_id"]:
                continue
            gap = b["first_frame"] - a["last_frame"]
            if gap < 1 or gap > AUDIT_GAP:
                continue
            dist = math.dist(
                (a["last_x"], a["last_y"]),
                (b["first_x"], b["first_y"]),
            )
            if dist >= CANDIDATE_DIST:
                continue
            within = gap <= CURRENT_GAP and dist < CURRENT_DIST
            candidates.append({
                "from_stable_id": a["stable_id"],
                "to_stable_id": b["stable_id"],
                "frame_gap": gap,
                "pixel_distance": round(dist, 2),
                "within_current_thresholds": within,
            })

    cand = pd.DataFrame(candidates)
    if not cand.empty:
        cand = cand.sort_values(["from_stable_id", "frame_gap", "pixel_distance"])
    cand.to_csv(out_dir / "fragmentation_candidates.csv", index=False)

    stats = {
        "total_frames": span_frames,
        "byte_track_ids": int(p["track_id"].nunique()),
        "stable_ids": int(p["stable_id"].nunique()),
        "stable_per_frame_min": int(per_frame.min()),
        "stable_per_frame_median": float(per_frame.median()),
        "stable_per_frame_max": int(per_frame.max()),
        "short_lived": int((audit["longevity"] == "short").sum()),
        "long_lived": int((audit["longevity"] == "long").sum()),
        "multi_track_stable": int((audit["track_id_count"] > 1).sum()),
        "fragment_pairs": len(cand),
        "within_threshold_pairs": (
            int(cand["within_current_thresholds"].sum()) if not cand.empty else 0
        ),
    }
    return stats


def main():
    parser = argparse.ArgumentParser(description="Audit player identity from coordinate CSV")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=IDENTITY_OUTPUT)
    args = parser.parse_args()
    stats = run_audit(args.csv, args.out)
    print("Identity audit summary:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  audit_csv: {args.out / 'identity_audit.csv'}")


if __name__ == "__main__":
    main()
