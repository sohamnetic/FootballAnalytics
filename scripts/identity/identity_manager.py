import csv
import math
from pathlib import Path

from config.config import (
    IDENTITY_APPEARANCE_MAX_HIST_DIST,
    IDENTITY_APPEARANCE_MIN_GAP_S,
    IDENTITY_BASE_SLACK_PX,
    IDENTITY_HEIGHT_RATIO_MIN_SAMPLES,
    IDENTITY_MAX_DISTANCE_CEILING_PX,
    IDENTITY_MAX_GAP_S,
    IDENTITY_MAX_HEIGHT_RATIO,
    IDENTITY_OUTPUT,
    IDENTITY_PX_PER_SECOND_BUDGET,
    IDENTITY_REMATCH_AUDIT,
)

from scripts.identity.player_profile import PlayerProfile
from scripts.vision.jersey_color import JerseyColorExtractor

# rough player height, only used for the height check
_REFERENCE_HEIGHT_M = 1.75


class IdentityManager:
    """
    Keeps a stable id for each player while the tracker ids keep changing.

    When a new track appears we try to match it to a player we lost recently:
    - distance allowed grows with the time they were gone (up to a max)
    - for longer gaps the shirt colour has to match too
    - box height can't be too different

    Teammates with the same shirt can still get confused.

    Call start_new_frame() every frame, then assign_frame() with all the
    detections of that frame (or get_stable_id() for one at a time).
    """

    def __init__(
        self,
        fps,
        max_gap_s=IDENTITY_MAX_GAP_S,
        base_slack_px=IDENTITY_BASE_SLACK_PX,
        px_per_second_budget=IDENTITY_PX_PER_SECOND_BUDGET,
        max_distance_ceiling_px=IDENTITY_MAX_DISTANCE_CEILING_PX,
        appearance_min_gap_s=IDENTITY_APPEARANCE_MIN_GAP_S,
        appearance_max_hist_dist=IDENTITY_APPEARANCE_MAX_HIST_DIST,
        max_height_ratio=IDENTITY_MAX_HEIGHT_RATIO,
        height_ratio_min_samples=IDENTITY_HEIGHT_RATIO_MIN_SAMPLES,
        enable_audit=IDENTITY_REMATCH_AUDIT,
        audit_path=None,
    ):
        if not fps or fps <= 0:
            raise ValueError("IdentityManager requires a positive fps")

        self.fps = float(fps)
        self.max_frame_gap = max(1, int(max_gap_s * self.fps + 0.5))
        self.base_slack_px = float(base_slack_px)
        self.px_per_second_budget = float(px_per_second_budget)
        self.max_distance_ceiling_px = float(max_distance_ceiling_px)
        self.appearance_min_gap_frames = max(1, int(appearance_min_gap_s * self.fps + 0.5))
        self.appearance_max_hist_dist = float(appearance_max_hist_dist)
        self.max_height_ratio = float(max_height_ratio)
        self.height_ratio_min_samples = int(height_ratio_min_samples)
        self.enable_audit = enable_audit
        self.audit_path = Path(audit_path) if audit_path else None

        self.players = {}
        self.track_to_stable = {}
        self.active_tracks = {}
        self.next_stable_id = 1

        self._extractor = JerseyColorExtractor()
        self._rematch_events = []

    # ==========================================================
    # Frame Management
    # ==========================================================

    def start_new_frame(self):
        self.active_tracks.clear()

    # ==========================================================
    # Appearance / geometry helpers
    # ==========================================================

    def _extract_descriptor(self, frame, bbox):
        if frame is None:
            return None
        return self._extractor.extract_descriptor(frame, bbox)

    def _update_profile_appearance(self, player, frame, bbox):
        if frame is not None:
            color = self._extractor.extract_color(frame, bbox)
            if color is not None:
                player.jersey_color = color if player.jersey_color is None else tuple(
                    int((a + b) / 2) for a, b in zip(player.jersey_color, color)
                )
            descriptor = self._extractor.extract_descriptor(frame, bbox)
            if descriptor is not None:
                player.jersey_descriptor = JerseyColorExtractor.descriptor_running_avg(
                    player.jersey_descriptor, descriptor
                )
        player.sample_count += 1

    def _max_distance(self, frame_gap):
        per_frame = self.px_per_second_budget / self.fps
        return min(
            self.base_slack_px + frame_gap * per_frame,
            self.max_distance_ceiling_px,
        )

    # ==========================================================
    # Audit logging
    # ==========================================================

    def _log_rematch_event(
        self,
        frame_number,
        new_track_id,
        candidate_stable_id,
        frame_gap,
        position_distance,
        allowed_distance,
        height_ratio,
        hist_distance,
        accepted,
        reason,
    ):
        if not self.enable_audit:
            return

        self._rematch_events.append({
            "frame": frame_number,
            "new_track_id": new_track_id,
            "candidate_stable_id": candidate_stable_id,
            "frame_gap": frame_gap if frame_gap is not None else "",
            "position_distance_px": (
                round(position_distance, 2) if position_distance is not None else ""
            ),
            "allowed_distance_px": (
                round(allowed_distance, 2) if allowed_distance is not None else ""
            ),
            "height_ratio": round(height_ratio, 3) if height_ratio is not None else "",
            "hist_distance": round(hist_distance, 3) if hist_distance is not None else "",
            "accepted": accepted,
            "reason": reason,
        })

    def write_rematch_audit(self, output_path=None):
        if not self._rematch_events:
            return None

        output_path = Path(output_path) if output_path else self.audit_path
        if output_path is None:
            IDENTITY_OUTPUT.mkdir(parents=True, exist_ok=True)
            output_path = IDENTITY_OUTPUT / "rematch_audit.csv"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "frame",
            "new_track_id",
            "candidate_stable_id",
            "frame_gap",
            "position_distance_px",
            "allowed_distance_px",
            "height_ratio",
            "hist_distance",
            "accepted",
            "reason",
        ]
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._rematch_events)

        return output_path

    # ==========================================================
    # Player Registration / update
    # ==========================================================

    def register_new_player(self, track_id, frame_number, position, bbox, frame=None):
        stable_id = self.next_stable_id
        self.next_stable_id += 1

        height = bbox[3] - bbox[1]

        profile = PlayerProfile(
            stable_id=stable_id,
            current_track_id=track_id,
            track_history=[track_id],
            first_seen_frame=frame_number,
            last_seen_frame=frame_number,
            last_position=position,
            bbox=bbox,
            average_height=height,
        )

        self._update_profile_appearance(profile, frame, bbox)

        self.players[stable_id] = profile
        self.track_to_stable[track_id] = stable_id
        self.active_tracks[track_id] = stable_id

        return stable_id

    def update_player(self, stable_id, frame_number, position, bbox, frame=None):
        player = self.players[stable_id]

        player.last_seen_frame = frame_number
        player.last_position = position
        player.bbox = bbox

        height = bbox[3] - bbox[1]
        player.average_height = (player.average_height + height) / 2

        self._update_profile_appearance(player, frame, bbox)

        self.active_tracks[player.current_track_id] = stable_id

    def _reassign_track(self, track_id, stable_id, frame_number, position, bbox, frame=None):
        player = self.players[stable_id]
        player.current_track_id = track_id
        player.track_history.append(track_id)

        self.track_to_stable[track_id] = stable_id
        self.active_tracks[track_id] = stable_id

        self.update_player(stable_id, frame_number, position, bbox, frame=frame)

    # ==========================================================
    # Candidate scoring
    # ==========================================================

    def _score_candidates(self, frame_number, position, bbox, descriptor, new_track_id):
        """
        Lost players this track could be, best match first.
        Returns (score, stable_id, gap, dist, allowed, ratio, hd) tuples.
        """
        height = bbox[3] - bbox[1]
        candidates = []

        for stable_id, player in self.players.items():
            if stable_id in self.active_tracks.values():
                continue

            frame_gap = frame_number - player.last_seen_frame
            if frame_gap <= 0 or frame_gap > self.max_frame_gap:
                continue

            distance = math.dist(position, player.last_position)
            allowed = self._max_distance(frame_gap)

            if distance >= allowed:
                if distance < allowed * 1.3:
                    self._log_rematch_event(
                        frame_number, new_track_id, stable_id, frame_gap,
                        distance, allowed, None, None, False, "distance_exceeded",
                    )
                continue

            ratio = None
            if (
                player.sample_count >= self.height_ratio_min_samples
                and player.average_height > 0
                and height > 0
            ):
                ratio = max(player.average_height, height) / min(player.average_height, height)
                if ratio > self.max_height_ratio:
                    self._log_rematch_event(
                        frame_number, new_track_id, stable_id, frame_gap,
                        distance, allowed, ratio, None, False, "height_ratio_incompatible",
                    )
                    continue

            hd = None
            if frame_gap > self.appearance_min_gap_frames:
                hd = JerseyColorExtractor.descriptor_distance(descriptor, player.jersey_descriptor)
                if hd is not None and hd > self.appearance_max_hist_dist:
                    self._log_rematch_event(
                        frame_number, new_track_id, stable_id, frame_gap,
                        distance, allowed, ratio, hd, False, "appearance_incompatible",
                    )
                    continue

            score = distance / max(allowed, 1.0)
            candidates.append((score, stable_id, frame_gap, distance, allowed, ratio, hd))

        candidates.sort(key=lambda c: c[0])
        return candidates

    # ==========================================================
    # Whole frame at once
    # ==========================================================

    def assign_frame(self, frame_number, detections, frame=None):
        """
        Get stable ids for all detections in a frame. Doing the whole frame
        together means if two new tracks could be the same lost player,
        the closer one gets it.

        detections: list of dicts with track_id, position (feet), bbox
        Returns {track_id: stable_id}
        """
        results = {}
        pending = []

        for det in detections:
            track_id = det["track_id"]
            position = det["position"]
            bbox = det["bbox"]

            if track_id in self.track_to_stable:
                stable_id = self.track_to_stable[track_id]
                self.update_player(stable_id, frame_number, position, bbox, frame=frame)
                results[track_id] = stable_id
            else:
                descriptor = self._extract_descriptor(frame, bbox)
                pending.append({
                    "track_id": track_id,
                    "position": position,
                    "bbox": bbox,
                    "descriptor": descriptor,
                })

        edges = []
        for det in pending:
            candidates = self._score_candidates(
                frame_number, det["position"], det["bbox"], det["descriptor"], det["track_id"],
            )
            for score, stable_id, gap, dist, allowed, ratio, hd in candidates:
                edges.append((score, det["track_id"], stable_id, det, gap, dist, allowed, ratio, hd))

        edges.sort(key=lambda e: e[0])
        used_tracks, used_stable = set(), set()
        for score, track_id, stable_id, det, gap, dist, allowed, ratio, hd in edges:
            if track_id in used_tracks or stable_id in used_stable:
                continue
            used_tracks.add(track_id)
            used_stable.add(stable_id)

            self._log_rematch_event(
                frame_number, track_id, stable_id, gap, dist, allowed, ratio, hd, True, "accepted",
            )
            self._reassign_track(
                track_id, stable_id, frame_number, det["position"], det["bbox"], frame=frame,
            )
            results[track_id] = stable_id

        for det in pending:
            track_id = det["track_id"]
            if track_id in results:
                continue
            results[track_id] = self.register_new_player(
                track_id, frame_number, det["position"], det["bbox"], frame=frame,
            )

        return results

    # ==========================================================
    # One detection at a time
    # ==========================================================

    def get_stable_id(self, track_id, frame_number, position, bbox, frame=None):
        if track_id in self.track_to_stable:
            stable_id = self.track_to_stable[track_id]
            self.update_player(stable_id, frame_number, position, bbox, frame=frame)
            return stable_id

        descriptor = self._extract_descriptor(frame, bbox)
        candidates = self._score_candidates(frame_number, position, bbox, descriptor, track_id)

        if candidates:
            _, stable_id, gap, dist, allowed, ratio, hd = candidates[0]
            self._log_rematch_event(
                frame_number, track_id, stable_id, gap, dist, allowed, ratio, hd, True, "accepted",
            )
            self._reassign_track(track_id, stable_id, frame_number, position, bbox, frame=frame)
            return stable_id

        return self.register_new_player(track_id, frame_number, position, bbox, frame=frame)
