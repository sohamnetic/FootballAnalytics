from pathlib import Path

from scripts.analytics.draw_trajectory import TrajectoryDrawer
from config.config import TEST_VIDEO

csv = Path("outputs/coordinates/match_test.csv")

drawer = TrajectoryDrawer(
    csv,
    TEST_VIDEO
)

drawer.draw(1)