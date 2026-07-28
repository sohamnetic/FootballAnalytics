import cv2
import os

# ======================================================
# CHANGE THIS TO YOUR VIDEO NAME
# Example:
# D:\FootballAnalytics\videos\raw\match.mp4
# ======================================================

video_path = r"D:\FootballAnalytics\videos\test\match_test.mp4"

# Check if video exists
if not os.path.exists(video_path):
    print("❌ Video not found!")
    print(f"Expected location: {video_path}")
    exit()

# Open the video
cap = cv2.VideoCapture(video_path)

# Check if video opened successfully
if not cap.isOpened():
    print("❌ Unable to open the video.")
    exit()

# Read video properties
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

# Calculate duration
duration_seconds = frame_count / fps
minutes = int(duration_seconds // 60)
seconds = int(duration_seconds % 60)

# Print information
print("=" * 60)
print("           FOOTBALL VIDEO INFORMATION")
print("=" * 60)

print(f"📁 Video Path      : {video_path}")
print(f"📺 Resolution      : {width} x {height}")
print(f"🎞 FPS             : {fps:.2f}")
print(f"🖼 Total Frames    : {frame_count}")
print(f"⏱ Duration        : {minutes} min {seconds} sec")
print(f"📦 Estimated Pixels per Frame : {width * height:,}")

print("=" * 60)

# Release video
cap.release()