from pathlib import Path

from scripts.analytics.distance import DistanceEngine

csv = Path("outputs/coordinates/match_test.csv")

engine = DistanceEngine(csv)

distance = engine.calculate_distance(1)

print("=" * 40)
print("Player 1 Distance")
print("=" * 40)
print(f"Pixel Distance : {distance:.2f}")