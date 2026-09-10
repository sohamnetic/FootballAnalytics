import csv
import math
from pathlib import Path

from config.config import (
    IDENTITY_APPEARANCE_MAX_BGR_DIST,
    IDENTITY_MAX_DISTANCE_PX,
    IDENTITY_MAX_FRAME_GAP,
    IDENTITY_OUTPUT,
    IDENTITY_REMATCH_AUDIT,
)

from scripts.identity.player_profile import PlayerProfile
from scripts.vision.jersey_color import JerseyColorExtractor


class IdentityManager:
    """
    Maintains stable player identities throughout a football match.

    Rematch uses last position + frame gap. Jersey colour is a soft
    rejection signal only (not a unique player identifier).
    """

    def __init__(
        self,
        max_frame_gap=IDENTITY_MAX_FRAME_GAP,
        max_distance=IDENTITY_MAX_DISTANCE_PX,
        appearance_max_bgr_dist=IDENTITY_APPEARANCE_MAX_BGR_DIST,
        enable_audit=IDENTITY_REMATCH_AUDIT,
        audit_path=None,
    ):
        self.max_frame_gap = int(max_frame_gap)
        self.max_distance = float(max_distance)
        self.appearance_max_bgr_dist = float(appearance_max_bgr_dist)
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
    # Appearance helpers
    # ==========================================================

    @staticmethod
    def _bgr_distance(color_a, color_b):
        if color_a is None or color_b is None:
            return None
        return math.dist(color_a, color_b)

    def _extract_jersey_color(self, frame, bbox):
        if frame is None:
            return None
        return self._extractor.extract_color(frame, bbox)

    def _update_profile_jersey(self, player, frame, bbox):
        color = self._extract_jersey_color(frame, bbox)
        if color is None:
            return

        if player.jersey_color is None:
            player.jersey_color = color
            return

        old = player.jersey_color
        player.jersey_color = tuple(
            int((a + b) / 2) for a, b in zip(old, color)
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
        appearance_diff,
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
                round(position_distance, 2)
                if position_distance is not None
                else ""
            ),
            "appearance_bgr_distance": (
                round(appearance_diff, 2)
                if appearance_diff is not None
                else ""
            ),
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
            "appearance_bgr_distance",
            "accepted",
            "reason",
        ]
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._rematch_events)

        return output_path

    # ==========================================================
    # Player Registration
    # ==========================================================

    def register_new_player(
        self,
        track_id,
        frame_number,
        position,
        bbox,
        frame=None,
    ):
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

        self._update_profile_jersey(profile, frame, bbox)

        self.players[stable_id] = profile
        self.track_to_stable[track_id] = stable_id
        self.active_tracks[track_id] = stable_id

        return stable_id

    # ==========================================================
    # Update Existing Player
    # ==========================================================

    def update_player(
        self,
        stable_id,
        frame_number,
        position,
        bbox,
        frame=None,
    ):
        player = self.players[stable_id]

        player.last_seen_frame = frame_number
        player.last_position = position
        player.bbox = bbox

        height = bbox[3] - bbox[1]
        player.average_height = (player.average_height + height) / 2

        self._update_profile_jersey(player, frame, bbox)

        self.active_tracks[player.current_track_id] = stable_id

    # ==========================================================
    # Rematch
    # ==========================================================

    def find_matching_player(
        self,
        frame_number,
        position,
        bbox,
        frame,
        new_track_id,
    ):
        current_jersey = self._extract_jersey_color(frame, bbox)

        best_match = None
        best_distance = float("inf")
        best_gap = None
        best_appearance = None

        for stable_id, player in self.players.items():
            frame_gap = frame_number - player.last_seen_frame

            if frame_gap > self.max_frame_gap:
                continue

            distance = math.dist(position, player.last_position)

            if stable_id in self.active_tracks.values():
                if distance < self.max_distance:
                    self._log_rematch_event(
                        frame_number,
                        new_track_id,
                        stable_id,
                        frame_gap,
                        distance,
                        None,
                        False,
                        "candidate_active",
                    )
                continue

            if distance >= self.max_distance:
                if distance < self.max_distance * 1.5:
                    self._log_rematch_event(
                        frame_number,
                        new_track_id,
                        stable_id,
                        frame_gap,
                        distance,
                        None,
                        False,
                        "distance_exceeded",
                    )
                continue

            appearance_diff = self._bgr_distance(
                current_jersey,
                player.jersey_color,
            )

            if (
                appearance_diff is not None
                and appearance_diff > self.appearance_max_bgr_dist
            ):
                self._log_rematch_event(
                    frame_number,
                    new_track_id,
                    stable_id,
                    frame_gap,
                    distance,
                    appearance_diff,
                    False,
                    "appearance_incompatible",
                )
                continue

            if distance < best_distance:
                best_distance = distance
                best_match = stable_id
                best_gap = frame_gap
                best_appearance = appearance_diff

        if best_match is not None:
            self._log_rematch_event(
                frame_number,
                new_track_id,
                best_match,
                best_gap,
                best_distance,
                best_appearance,
                True,
                "accepted",
            )

        return best_match

    # ==========================================================
    # Main Function
    # ==========================================================

    def get_stable_id(
        self,
        track_id,
        frame_number,
        position,
        bbox,
        frame=None,
    ):
        if track_id in self.track_to_stable:
            stable_id = self.track_to_stable[track_id]
            self.update_player(
                stable_id,
                frame_number,
                position,
                bbox,
                frame=frame,
            )
            return stable_id

        matched_player = self.find_matching_player(
            frame_number,
            position,
            bbox,
            frame,
            new_track_id=track_id,
        )

        if matched_player is not None:
            player = self.players[matched_player]

            player.current_track_id = track_id
            player.track_history.append(track_id)

            self.track_to_stable[track_id] = matched_player
            self.active_tracks[track_id] = matched_player

            self.update_player(
                matched_player,
                frame_number,
                position,
                bbox,
                frame=frame,
            )

            return matched_player

        return self.register_new_player(
            track_id,
            frame_number,
            position,
            bbox,
            frame=frame,
        )
