from Detector_esp32 import Detector
import os
import sys

# ── Input Source ──────────────────────────────────────────────────────────────
#   "esp32"   → live ESP32-CAM (auto-tries 3 connection methods)
#   "webcam"  → laptop / USB webcam
#   "video"   → local MP4 file in test_videos/
INPUT_SOURCE = "esp32"


def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))

    if INPUT_SOURCE == "esp32":
        video_path = "http://10.171.25.8"
        print("[INFO] Mode: ESP32-CAM  (will auto-try 3 connection methods)")

    elif INPUT_SOURCE == "webcam":
        video_path = 0
        print("[INFO] Mode: Webcam (device 0)")

    elif INPUT_SOURCE == "video":
        video_path = os.path.join(current_dir, "test_videos", "test1.mp4")
        if not os.path.exists(video_path):
            print(f"[ERROR] Video file not found: {video_path}")
            sys.exit(1)
        print(f"[INFO] Mode: Local video → {video_path}")

    else:
        print(f"[ERROR] Unknown INPUT_SOURCE '{INPUT_SOURCE}'.")
        sys.exit(1)

    detector = Detector(video_path)
    detector.onvideo()


if __name__ == "__main__":
    main()