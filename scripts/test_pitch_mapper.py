from pathlib import Path
import cv2

from scripts.analytics.pitch_mapper import PitchMapper

csv = Path("outputs/coordinates/match_test.csv")

pitch = Path("assets/pitch.png")

mapper = PitchMapper(csv, pitch)

image = mapper.draw(1)

cv2.imshow("Football Pitch", image)

cv2.waitKey(0)

cv2.destroyAllWindows()