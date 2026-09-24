"""
Event time windows in frames for one video.

Thresholds live in config.py as seconds; every engine converts them with
the real fps of the video it is processing, so a 30 fps upload gets the
same time windows as the 60 fps footage they were tuned on.
"""
from dataclasses import dataclass

from config.config import (
    INTERCEPTION_MAX_TRANSITION_S,
    MAX_BALL_INTERPOLATION_GAP_S,
    PASS_MAX_TRANSITION_S,
    PASS_MIN_POSSESSION_S,
    POSSESSION_CONFIRM_S,
    POSSESSION_MERGE_GAP_S,
    RECOVERY_MAX_TRANSITION_S,
    GOAL_MIN_INSIDE_S,
    GOAL_VANISH_S,
    SHOT_AIM_S,
    SHOT_MIN_POSSESSION_S,
    SHOT_WINDOW_S,
)


def frames_for(seconds, fps):
    return max(1, int(seconds * fps + 0.5))


@dataclass(frozen=True)
class EventTiming:
    fps: float

    def f(self, seconds):
        return frames_for(seconds, self.fps)

    @property
    def ball_interpolation_gap(self):
        return self.f(MAX_BALL_INTERPOLATION_GAP_S)

    @property
    def possession_confirm(self):
        return self.f(POSSESSION_CONFIRM_S)

    @property
    def possession_merge_gap(self):
        return self.f(POSSESSION_MERGE_GAP_S)

    @property
    def pass_max_transition(self):
        return self.f(PASS_MAX_TRANSITION_S)

    @property
    def pass_min_possession(self):
        return self.f(PASS_MIN_POSSESSION_S)

    @property
    def interception_max_transition(self):
        return self.f(INTERCEPTION_MAX_TRANSITION_S)

    @property
    def recovery_max_transition(self):
        return self.f(RECOVERY_MAX_TRANSITION_S)

    @property
    def shot_min_possession(self):
        return self.f(SHOT_MIN_POSSESSION_S)

    @property
    def shot_window(self):
        return self.f(SHOT_WINDOW_S)

    @property
    def shot_aim(self):
        return self.f(SHOT_AIM_S)

    @property
    def goal_min_inside(self):
        return self.f(GOAL_MIN_INSIDE_S)

    @property
    def goal_vanish(self):
        return self.f(GOAL_VANISH_S)

    # confidence heuristics (were 10 / 20 / 15 frames at 59.94 fps)
    @property
    def quick_transition(self):
        return self.f(0.17)

    @property
    def medium_transition(self):
        return self.f(0.33)

    @property
    def settled_possession(self):
        return self.f(0.25)
