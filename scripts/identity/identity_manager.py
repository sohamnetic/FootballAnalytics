import math

from scripts.identity.player_profile import PlayerProfile


class IdentityManager:
    """
    Maintains stable player identities throughout a football match.
    """

    def __init__(self):

        # Stable ID -> Player Profile
        self.players = {}

        # ByteTrack ID -> Stable ID
        self.track_to_stable = {}

        # Active tracks in the CURRENT frame
        self.active_tracks = {}

        # Counter for assigning new Stable IDs
        self.next_stable_id = 1

    # ==========================================================
    # Frame Management
    # ==========================================================

    def start_new_frame(self):
        """
        Call this at the beginning of every frame.
        """
        self.active_tracks.clear()

    # ==========================================================
    # Player Registration
    # ==========================================================

    def register_new_player(
        self,
        track_id,
        frame_number,
        position,
        bbox
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
            average_height=height
        )

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
        bbox
    ):

        player = self.players[stable_id]

        player.last_seen_frame = frame_number
        player.last_position = position
        player.bbox = bbox

        height = bbox[3] - bbox[1]

        player.average_height = (
            player.average_height + height
        ) / 2

        self.active_tracks[player.current_track_id] = stable_id

    # ==========================================================
    # Future Matching Function
    # ==========================================================

    def find_matching_player(
        self,
        frame_number,
        position,
        max_frame_gap=60,
        max_distance=120
    ):
        """
        Finds a previously seen player that could match a newly
        appeared ByteTrack ID.

        (Currently only checks time and distance.)
        """

        best_match = None
        best_distance = float("inf")

        for stable_id, player in self.players.items():

            # Ignore players currently visible
            if stable_id in self.active_tracks.values():
                continue

            frame_gap = frame_number - player.last_seen_frame

            if frame_gap > max_frame_gap:
                continue

            distance = math.dist(
                position,
                player.last_position
            )

            if distance < max_distance and distance < best_distance:

                best_distance = distance
                best_match = stable_id

        return best_match

    # ==========================================================
    # Main Function
    # ==========================================================

    def get_stable_id(
        self,
        track_id,
        frame_number,
        position,
        bbox
    ):

        # Existing ByteTrack ID
        if track_id in self.track_to_stable:

            stable_id = self.track_to_stable[track_id]

            self.update_player(
                stable_id,
                frame_number,
                position,
                bbox
            )

            return stable_id

        # ------------------------------------------------------
        # Future:
        # Try to match with a disappeared player
        # ------------------------------------------------------

        matched_player = self.find_matching_player(
            frame_number,
            position
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
                bbox
            )

            return matched_player

        # ------------------------------------------------------
        # No Match Found
        # Create New Player
        # ------------------------------------------------------

        return self.register_new_player(
            track_id,
            frame_number,
            position,
            bbox
        )