from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class PlayerProfile:
    """
    Stores information about one real player throughout the match.
    """

    stable_id: int

    # Current ByteTrack ID
    current_track_id: int

    # Previous ByteTrack IDs assigned to this player
    track_history: List[int] = field(default_factory=list)

    # Frame information
    first_seen_frame: int = 0
    last_seen_frame: int = 0

    # Bottom-centre position (player's feet)
    last_position: Tuple[int, int] = (0, 0)

    # Bounding box
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)

    # Running average player height (pixels)
    average_height: float = 0.0

    # Future features
    jersey_color = None
    appearance_embedding = None