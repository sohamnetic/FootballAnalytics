"""
Offline identity resolution: raw tracker tracklets -> player identities.

Online trackers (ByteTrack) fragment a player every time they are occluded,
missed by the detector for too long, or leave the view while the camera
pans - 90-110 fragments for ~13 people on a 40s clip. This module works on
the whole clip at once, after tracking:

1. Player gate: a tracklet is a player only if the person stands on turf
   and wears a saturated kit colour. Removes spectators, bench, staff and
   false detections (boards, netting), which the fixed-pixel pitch polygon
   could not do on a panning camera.
2. Kit group: dominant torso hue (turf pixels excluded). Different kits
   never merge.
3. Constrained agglomerative clustering. Cost = average-linkage person-ReID
   distance, minus a bonus when jersey-number OCR agrees, plus a penalty
   when the camera-motion-compensated position jump between consecutive
   fragments is implausible. Hard cannot-links: two tracklets that are
   visible at the same time as clearly different boxes, different kit
   groups, and confidently different jersey numbers.
   Phase 1 merges while cost < IDENTITY_MERGE_COST. Phase 2 keeps merging
   a kit group (up to IDENTITY_FORCED_MERGE_COST) only while it still has
   more identities than the most players of that kit ever seen at once.

Identities are still an estimate: same-kit teammates with no readable
number are separated by ReID + motion only. See docs/architecture.md.
"""
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from config.config import (
    IDENTITY_FORCED_MERGE_COST,
    IDENTITY_KIT_MIN_SAT,
    IDENTITY_MERGE_COST,
    IDENTITY_MIN_TRACKLET_DETECTIONS,
    IDENTITY_OCR_MIN_CONF,
    IDENTITY_PLAYER_TURF_MIN,
    IDENTITY_PLAYER_TURF_MIN_STRONG_KIT,
    IDENTITY_STRONG_KIT_SAT,
    IDENTITY_STABILIZED_SPEED_PX_S,
)

_OVERLAP_IOU_SAME_BOX = 0.5
_MAX_CONFLICT_FRAMES = 2
_MOTION_WEIGHT = 0.35
_OCR_BONUS = {2: 0.30, 1: 0.10}


@dataclass
class Tracklet:
    track_id: int
    rows: np.ndarray
    start: int
    end: int
    n: int
    turf: float
    sat: float
    kit: int = -1
    emb: np.ndarray = None
    number: str = None
    number_weight: float = 0.0
    number_strong: bool = False
    p_start: np.ndarray = None
    p_end: np.ndarray = None
    v_end: np.ndarray = None
    is_player: bool = False
    drop_reason: str = ""


@dataclass
class Resolution:
    identity_of: dict                       # track_id -> identity (players only)
    tracklets: dict                         # track_id -> Tracklet
    headcount: dict                         # kit bin -> max concurrent players
    merges: list = field(default_factory=list)

    def report(self):
        by_id = defaultdict(list)
        for tid, ident in self.identity_of.items():
            by_id[ident].append(tid)
        identities = []
        for ident in sorted(by_id):
            ts = sorted(by_id[ident], key=lambda t: self.tracklets[t].start)
            nums = sorted({self.tracklets[t].number for t in ts if self.tracklets[t].number})
            identities.append({
                "identity": ident,
                "tracklet_numbers": {
                    str(t): [self.tracklets[t].number, round(self.tracklets[t].number_weight, 2),
                             self.tracklets[t].number_strong]
                    for t in ts if self.tracklets[t].number
                },
                "kit_hue_bin": self.tracklets[ts[0]].kit,
                "jersey_number_ocr": nums,
                "tracklets": ts,
                "detections": int(sum(self.tracklets[t].n for t in ts)),
                "first_frame": min(self.tracklets[t].start for t in ts),
                "last_frame": max(self.tracklets[t].end for t in ts),
            })
        dropped = [
            {"track_id": t.track_id, "detections": t.n, "reason": t.drop_reason,
             "turf": round(t.turf, 3), "kit_saturation": round(t.sat, 3)}
            for t in self.tracklets.values() if not t.is_player
        ]
        return {
            "raw_tracklets": len(self.tracklets),
            "player_tracklets": sum(t.is_player for t in self.tracklets.values()),
            "identities": len(by_id),
            "headcount_by_kit": {str(k): v for k, v in self.headcount.items()},
            "identity_detail": identities,
            "dropped_tracklets": sorted(dropped, key=lambda d: -d["detections"]),
            "merges": self.merges,
        }


def normalize_number(text):
    # 1 and 7 are the dominant OCR confusion on jersey fonts (#10 read as 70)
    return text.replace("7", "1")


def rank_number_votes(weights):
    """
    weights: {normalized number: summed OCR confidence}.
    Returns (number, support, rival): partial reads ("2" of "12") add half
    their weight to the longer number; rival is the best incompatible read.
    """
    if not weights:
        return None, 0.0, 0.0
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    top, support = ranked[0]
    support += 0.5 * sum(w for k, w in ranked[1:] if k in top)
    rival = max([w for k, w in ranked[1:] if k not in top and top not in k] or [0.0])
    return top, support, rival


def _tracklet_number(reads):
    """(number, support, strong). Usable numbers earn a merge bonus; only
    strong ones may veto a merge, since a false veto splits a player."""
    weights = defaultdict(float)
    for text, conf in reads:
        if conf >= IDENTITY_OCR_MIN_CONF:
            weights[normalize_number(text)] += conf
    top, support, rival = rank_number_votes(weights)
    if top is None or support < 3.0 or support < 1.5 * rival:
        return None, 0.0, False
    return top, support, support >= 5.0 and support >= 2.5 * rival


def _number_relation(nums_a, nums_b):
    """nums_*: {number: strong}. -1 conflict (both strong, incompatible),
    2 same full number, 1 compatible partial, 0 no usable evidence."""
    rel = 0
    for a, strong_a in nums_a.items():
        for b, strong_b in nums_b.items():
            if a == b:
                rel = max(rel, 2 if len(a) >= 2 else 1)
            elif a in b or b in a:
                rel = max(rel, 1)
            elif strong_a and strong_b:
                return -1
    return rel


def _build_tracklets(features):
    rows = features["rows"]
    feet = np.stack([(rows[:, 3] + rows[:, 5]) / 2, rows[:, 6], np.ones(len(rows))], axis=1)
    cams = features["camera"]
    stab = np.array([cams[int(f)] @ p for f, p in zip(rows[:, 0], feet)])[:, :2] if len(rows) else np.zeros((0, 2))
    heights = rows[:, 6] - rows[:, 4]

    reads = defaultdict(list)
    for tid, _, text, conf in features["ocr_reads"]:
        reads[int(tid)].append((text, conf))

    track_emb = features["track_emb"]
    tracklets = {}
    for tid in (int(t) for t in np.unique(rows[:, 1])):
        idx = np.flatnonzero(rows[:, 1] == tid)
        idx = idx[np.argsort(rows[idx, 0], kind="stable")]
        t = Tracklet(
            track_id=tid, rows=idx, start=int(rows[idx[0], 0]), end=int(rows[idx[-1], 0]),
            n=len(idx), turf=float(np.median(features["turf"][idx])),
            sat=float(np.median(features["kit_sat"][idx])),
        )

        hist = (features["kit_hist"][idx] * np.clip(heights[idx], 40, 250)[:, None]).sum(0)
        hist[0] += hist[-1]      # red wraps around the hue circle
        hist[-1] = 0
        t.kit = int(hist.argmax())

        t.emb = track_emb.get(tid)

        t.number, t.number_weight, t.number_strong = _tracklet_number(reads.get(tid, []))

        pos = stab[idx]
        t.p_start, t.p_end = pos[0], pos[-1]
        tail = idx[-min(15, len(idx)):]
        span = max(rows[tail[-1], 0] - rows[tail[0], 0], 1)
        t.v_end = (stab[tail[-1]] - stab[tail[0]]) / span

        if t.n < IDENTITY_MIN_TRACKLET_DETECTIONS:
            t.drop_reason = "too_short"
        elif not (
            (t.turf >= IDENTITY_PLAYER_TURF_MIN and t.sat >= IDENTITY_KIT_MIN_SAT)
            or (t.turf >= IDENTITY_PLAYER_TURF_MIN_STRONG_KIT and t.sat >= IDENTITY_STRONG_KIT_SAT)
        ):
            t.drop_reason = "off_pitch_or_no_kit"
        else:
            t.is_player = True
        tracklets[tid] = t
    return tracklets


def _real_overlap_frames(rows, a, b):
    fa, fb = rows[a.rows, 0], rows[b.rows, 0]
    common, ia, ib = np.intersect1d(fa, fb, assume_unique=True, return_indices=True)
    if not len(common):
        return 0
    A, B = rows[a.rows[ia], 3:7], rows[b.rows[ib], 3:7]
    ix = np.clip(np.minimum(A[:, 2], B[:, 2]) - np.maximum(A[:, 0], B[:, 0]), 0, None)
    iy = np.clip(np.minimum(A[:, 3], B[:, 3]) - np.maximum(A[:, 1], B[:, 1]), 0, None)
    inter = ix * iy
    union = (A[:, 2] - A[:, 0]) * (A[:, 3] - A[:, 1]) + (B[:, 2] - B[:, 0]) * (B[:, 3] - B[:, 1]) - inter
    # overlapping boxes of the same size/place are a duplicate or merged box, not two people
    return int(((inter / np.maximum(union, 1.0)) < _OVERLAP_IOU_SAME_BOX).sum())


def _headcount(players, rows, fps):
    per_kit = defaultdict(lambda: defaultdict(int))
    for t in players:
        for f in np.unique(rows[t.rows, 0]):
            per_kit[t.kit][int(f)] += 1
    out = {}
    for kit, counts in per_kit.items():
        support = defaultdict(int)
        for c in counts.values():
            support[c] += 1
        # a headcount must hold for ~0.25s, not a one-frame duplicate box
        stable = [c for c, frames in support.items() if frames >= max(1, int(0.25 * fps))]
        out[kit] = max(stable) if stable else max(support)
    return out


def resolve_identities(features, fps):
    rows = features["rows"]
    tracklets = _build_tracklets(features)
    players = sorted((t for t in tracklets.values() if t.is_player), key=lambda t: t.start)
    n = len(players)
    if n == 0:
        return Resolution({}, tracklets, {})

    dim = next((t.emb.shape[0] for t in players if t.emb is not None), 1)
    E = np.stack([t.emb if t.emb is not None else np.zeros(dim) for t in players])
    has = np.array([t.emb is not None for t in players], float)

    conflict = np.zeros((n, n), bool)
    for i in range(n):
        for j in range(i + 1, n):
            c = players[i].kit != players[j].kit or _real_overlap_frames(rows, players[i], players[j]) > _MAX_CONFLICT_FRAMES
            conflict[i, j] = conflict[j, i] = c
    np.fill_diagonal(conflict, True)

    # cluster state, indexed by the position of the cluster's first tracklet
    members = {i: [i] for i in range(n)}
    sums = E.copy()
    counts = has.copy()
    nums = {i: ({players[i].number: players[i].number_strong} if players[i].number else {}) for i in range(n)}
    active = np.ones(n, bool)
    blocked = np.zeros((n, n), bool)

    # average-linkage appearance distance; only a merged cluster's row changes
    centroids = np.zeros_like(sums)
    np.divide(sums, counts[:, None], out=centroids, where=counts[:, None] > 0)
    app = 1.0 - centroids @ centroids.T
    app[counts == 0, :] = 1.0
    app[:, counts == 0] = 1.0

    # jersey-number relation (-1 conflict, 1 partial, 2 same), sparse in practice
    rel = np.zeros((n, n), np.int8)
    numbered = [i for i in range(n) if nums[i]]
    for x, i in enumerate(numbered):
        for j in numbered[x + 1:]:
            rel[i, j] = rel[j, i] = _number_relation(nums[i], nums[j])

    bonus_of = np.zeros(3, float)
    bonus_of[1], bonus_of[2] = _OCR_BONUS[1], _OCR_BONUS[2]

    def motion(a, b):
        seq = sorted([(players[i].start, i, 0) for i in members[a]] + [(players[i].start, i, 1) for i in members[b]])
        costs = []
        for (_, i, ca), (_, j, cb) in zip(seq, seq[1:]):
            if ca == cb:
                continue
            ti, tj = players[i], players[j]
            gap = tj.start - ti.end
            if gap <= 0:
                continue
            pred = ti.p_end + ti.v_end * min(gap, max(1, int(0.5 * fps)))
            allowed = 60.0 + IDENTITY_STABILIZED_SPEED_PX_S * gap / fps
            costs.append(min(float(np.linalg.norm(tj.p_start - pred) / allowed), 3.0))
        return float(np.mean(costs)) if costs else 0.0

    kits = np.array([t.kit for t in players])
    log = []

    def merge(a, b):
        members[a] += members.pop(b)
        sums[a] += sums[b]
        counts[a] += counts[b]
        for k, strong in nums[b].items():
            nums[a][k] = nums[a].get(k, False) or strong
        active[b] = False
        conflict[a, :] |= conflict[b, :]
        conflict[:, a] = conflict[a, :]
        conflict[a, a] = True
        blocked[a, :] = blocked[:, a] = False
        if counts[a] > 0:
            centroids[a] = sums[a] / counts[a]
            row = 1.0 - centroids @ centroids[a]
            row[counts == 0] = 1.0
            app[a, :] = app[:, a] = row
        for j in np.flatnonzero(active):
            if j != a and nums[j] and nums[a]:
                rel[a, j] = rel[j, a] = _number_relation(nums[a], nums[j])

    def merge_loop(threshold, kit=None, target=None):
        while True:
            live = active & ((kits == kit) if kit is not None else True)
            if target is not None and live.sum() <= target:
                return
            cost = app - bonus_of[np.clip(rel, 0, 2)]
            invalid = conflict | blocked | (rel < 0) | ~np.outer(live, live)
            cost = np.where(invalid, np.inf, cost)
            cost[np.tril_indices(n)] = np.inf
            a, b = np.unravel_index(np.argmin(cost), cost.shape)
            c = cost[a, b]
            if not np.isfinite(c) or c > threshold:
                return
            m = motion(a, b)
            total = c + _MOTION_WEIGHT * max(0.0, m - 1.0)
            if total > threshold:
                blocked[a, b] = blocked[b, a] = True
                continue
            relation = int(rel[a, b])
            merge(a, b)
            log.append({
                "phase": "forced" if target is not None else "confident",
                "cost": round(float(total), 3), "ocr_relation": relation, "motion": round(m, 2),
                "tracklets": sorted(players[i].track_id for i in members[a]),
            })

    merge_loop(IDENTITY_MERGE_COST)
    headcount = _headcount(players, rows, fps)
    for kit, target in sorted(headcount.items()):
        merge_loop(IDENTITY_FORCED_MERGE_COST, kit=kit, target=target)

    clusters = sorted(
        (members[a] for a in np.flatnonzero(active)),
        key=lambda m: (players[m[0]].kit, -sum(players[i].n for i in m)),
    )
    identity_of = {
        int(players[i].track_id): ident for ident, m in enumerate(clusters, start=1) for i in m
    }
    return Resolution(identity_of, tracklets, headcount, log)
