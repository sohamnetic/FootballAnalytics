from pathlib import Path

from scripts.analytics.trajectory import TrajectoryEngine

csv_path = Path("outputs/coordinates/match_test.csv")

engine = TrajectoryEngine(csv_path)

trajectory = engine.get_player_trajectory(1)

print("Total Positions :", len(trajectory))

print("First 10 Positions")

for p in trajectory[:10]:
    print(p)