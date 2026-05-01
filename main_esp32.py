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
    model_dir   = os.path.join(current_dir, "model_data")

    config_path  = os.path.join(model_dir, "ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt")
    model_path   = os.path.join(model_dir, "frozen_inference_graph.pb")
    classes_path = os.path.join(model_dir, "coco.names")

    missing = [p for p in [config_path, model_path, classes_path]
               if not os.path.exists(p)]
    if missing:
        print("[ERROR] Missing model file(s):")
        for p in missing:
            print(f"  • {p}")
        sys.exit(1)

    if INPUT_SOURCE == "esp32":
        # IP confirmed from browser — Detector handles all connection methods
        video_path = "http://10.171.25.8"
        print(f"[INFO] Mode: ESP32-CAM  (will auto-try 3 connection methods)")

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

    detector = Detector(video_path, config_path, model_path, classes_path)
    detector.onvideo()


if __name__ == "__main__":
    main()