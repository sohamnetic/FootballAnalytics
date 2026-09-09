from pathlib import Path

from scripts.analytics.smoothing import TrajectorySmoother

csv = Path("outputs/coordinates/match_test.csv")

engine = TrajectorySmoother(csv)

player = engine.smooth(1)

print("=" * 50)
print("Original vs Smoothed")
print("=" * 50)

print(player[
    [
        "center_x",
        "center_y",
        "smooth_x",
        "smooth_y"
    ]
].head(10))