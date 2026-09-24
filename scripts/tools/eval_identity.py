"""
Score a coordinate CSV's stable_id against hand-verified identity points.

Ground truth (data/identity_gt/*.csv) is `frame,x,y,label`: at that frame,
the person whose box contains (x, y) is `label`. It is keyed by position,
not tracker id, so it stays valid when detector/tracker settings change.

  python -m scripts.tools.eval_identity \
      --csv outputs/coordinates/match_t200_d40.csv \
      --gt data/identity_gt/match_t200_d40.csv

Pairwise over GT points: precision = same stable_id pairs that are truly
the same player; recall = same-player pairs that got the same stable_id.
"""
import argparse
from itertools import combinations
from pathlib import Path

import pandas as pd


def evaluate(csv_path, gt_path):
    df = pd.read_csv(csv_path)
    people = df[df["class"] == "person"]
    gt = pd.read_csv(gt_path)

    predicted, missing = [], 0
    by_frame = dict(tuple(people.groupby("frame")))
    for p in gt.itertuples(index=False):
        rows = by_frame.get(p.frame)
        hit = None
        if rows is not None:
            inside = rows[(rows.x1 <= p.x) & (p.x <= rows.x2) & (rows.y1 <= p.y) & (p.y <= rows.y2)]
            if len(inside):
                # GT points are box centres: with overlapping players, the
                # nearest centre is the person the point was placed on
                dist = ((inside.x1 + inside.x2) / 2 - p.x) ** 2 + ((inside.y1 + inside.y2) / 2 - p.y) ** 2
                hit = inside.loc[dist.idxmin(), "stable_id"]
        if hit is None or pd.isna(hit):
            missing += 1
        else:
            predicted.append((p.label, int(hit)))

    tp = fp = fn = 0
    for (la, ia), (lb, ib) in combinations(predicted, 2):
        same_truth, same_pred = la == lb, ia == ib
        tp += same_truth and same_pred
        fp += same_pred and not same_truth
        fn += same_truth and not same_pred

    frag = pd.DataFrame(predicted, columns=["label", "stable_id"]).groupby("label").stable_id.nunique()
    return {
        "gt_points": len(gt),
        "matched_points": len(predicted),
        "unmatched_points": missing,
        "pairwise_precision": round(tp / max(tp + fp, 1), 4),
        "pairwise_recall": round(tp / max(tp + fn, 1), 4),
        "ids_per_true_player": frag.to_dict(),
        "stable_ids_in_csv": int(people.stable_id.nunique()),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--gt", type=Path, required=True)
    args = ap.parse_args()
    for k, v in evaluate(args.csv, args.gt).items():
        print(f"{k:22s}: {v}")


if __name__ == "__main__":
    main()
