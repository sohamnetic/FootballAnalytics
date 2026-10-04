"""Player ratings: who comes out on top, and how time on screen and
goalkeeping are handled."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from config.config import RATING_BASE
from scripts.analytics.player_rating import add_ratings, rate


def player(sid, team="team_a", passes=0, interceptions=0, recoveries=0, on_ball=0.0):
    return {"stable_id": sid, "team_id": team, "successful_passes": passes, "interceptions": interceptions,
            "ball_recoveries": recoveries, "ball_possession_time_seconds": on_ball}


class RateTest(unittest.TestCase):
    def test_idle_player_stays_at_base(self):
        rating, confidence, breakdown = rate({}, 0.0, 600)
        self.assertEqual(rating, RATING_BASE)
        self.assertEqual(breakdown, [])

    def test_scorer_beats_passer_beats_idle(self):
        scorer, _, _ = rate({"goal": 1, "shot_on_target": 0}, 5, 600)
        passer, _, _ = rate({"pass": 6, "pass_received": 4}, 5, 600)
        idle, _, _ = rate({}, 0, 600)
        self.assertGreater(scorer, passer)
        self.assertGreater(passer, idle)

    def test_same_actions_over_more_time_count_less(self):
        short, _, _ = rate({"interception": 3}, 0, 120)
        long, _, _ = rate({"interception": 3}, 0, 1800)
        self.assertGreater(short, long)
        self.assertGreater(long, RATING_BASE)

    def test_goal_is_worth_the_same_in_a_long_match(self):
        short, _, _ = rate({"goal": 1}, 0, 120)
        long, _, _ = rate({"goal": 1}, 0, 1800)
        self.assertEqual(short, long)

    def test_losing_the_ball_lowers_the_rating(self):
        rating, _, breakdown = rate({"ball_lost": 3}, 0, 300)
        self.assertLess(rating, RATING_BASE)
        self.assertEqual(breakdown[0]["label"], "Ball lost")

    def test_rating_stays_between_3_and_10(self):
        self.assertEqual(rate({"goal": 9, "save": 5}, 0, 600)[0], 10.0)
        self.assertEqual(rate({"ball_lost": 40}, 0, 60)[0], 3.0)

    def test_little_screen_time_is_low_confidence(self):
        self.assertEqual(rate({}, 0, 60)[1], "low")
        self.assertEqual(rate({}, 0, 600)[1], "normal")

    def test_breakdown_adds_up_to_the_rating(self):
        rating, _, breakdown = rate({"pass": 4, "interception": 2, "ball_lost": 1, "goal": 1}, 12, 400)
        self.assertAlmostEqual(RATING_BASE + sum(b["points"] for b in breakdown), rating, delta=0.06)


class AddRatingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # players 1, 2 and 9 seen 4500 frames (150 s at 30 fps), player 3 only 30 (1 s)
        rows = [{"frame": f, "stable_id": sid, "class": "person"}
                for sid, n in ((1, 4500), (2, 4500), (9, 4500), (3, 30)) for f in range(n)]
        self.coords = Path(self.tmp.name) / "coords.csv"
        pd.DataFrame(rows).to_csv(self.coords, index=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_keeper_save_shooter_and_ball_loss(self):
        players = {1: player(1, passes=3), 2: player(2, interceptions=1), 9: player(9, "team_b"), 3: player(3)}
        teams = pd.DataFrame({"stable_id": [1, 2, 9, 3], "team_id": ["team_a", "team_a", "team_b", "team_a"],
                              "reason": ["kit group", "kit group", "goalkeeper (80% near goal; 3 distributions)", "kit group"]})
        passes = pd.DataFrame({"passer_stable_id": [1, 1, 1], "receiver_stable_id": [2, 2, 3]})
        intercepts = pd.DataFrame({"interceptor_stable_id": [2], "opponent_stable_id": [9]})
        shots = pd.DataFrame({"shooter_stable_id": [1], "outcome": ["saved"], "stopped_by_stable_id": [9],
                              "on_target": [True], "goal": [False]})
        best = add_ratings(players, passes_df=passes, intercepts_df=intercepts, shots_df=shots,
                           teams_df=teams, coordinate_csv=self.coords, fps=30)

        self.assertTrue(players[9]["is_goalkeeper"])
        self.assertEqual(players[9]["saves"], 1)
        self.assertEqual(players[9]["ball_losses"], 1)
        self.assertEqual(players[2]["passes_received"], 2)
        self.assertEqual(players[1]["visible_seconds"], 150.0)
        self.assertEqual(players[3]["rating_confidence"], "low")
        self.assertGreater(players[1]["rating"], RATING_BASE)  # shot on target + passes
        self.assertIn(best, (1, 2, 9))
        self.assertNotEqual(best, 3)

    def test_old_files_without_new_columns(self):
        players = {1: player(1)}
        shots = pd.DataFrame({"shooter_stable_id": [1], "on_target": ["True"], "goal": ["True"]})
        add_ratings(players, passes_df=pd.DataFrame(), intercepts_df=pd.DataFrame(), shots_df=shots,
                    teams_df=pd.DataFrame(), coordinate_csv=None, fps=30)
        self.assertEqual(players[1]["rating_breakdown"][0]["label"], "Goals")


if __name__ == "__main__":
    unittest.main()
