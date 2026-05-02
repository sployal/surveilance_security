import cv2
import mediapipe as mp
import numpy as np
import time
import urllib.request
import urllib.error
import socket

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 1: OpenCV VideoCapture
# ─────────────────────────────────────────────────────────────────────────────
def try_opencv_capture(url: str, timeout_sec: int = 8):
    print(f"[Method 1] Trying OpenCV VideoCapture → {url}")
    cap = cv2.VideoCapture(url)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_sec * 1000)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_sec * 1000)
    if cap.isOpened():
        ok, frame = cap.read()
        if ok and frame is not None:
            print("[Method 1] ✓ OpenCV VideoCapture works!")
            return cap
        cap.release()
    print("[Method 1] ✗ Failed.")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 2: requests library streaming
# ─────────────────────────────────────────────────────────────────────────────
class RequestsStream:
    JPEG_SOI = b'\xff\xd8'
    JPEG_EOI = b'\xff\xd9'

    def __init__(self, url: str, timeout: int = 15):
        self.url     = url
        self.timeout = timeout
        self._resp   = None
        self._iter   = None
        self._buffer = b''

    def connect(self) -> bool:
        if not HAS_REQUESTS:
            print("[Method 2] requests library not installed.")
            return False
        try:
            self._resp = requests.get(
                self.url, stream=True, timeout=self.timeout,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if self._resp.status_code == 200:
                self._iter = self._resp.iter_content(chunk_size=4096)
                print(f"[Method 2] ✓ requests connected → {self.url}")
                return True
            print(f"[Method 2] HTTP {self._resp.status_code}")
            return False
        except Exception as e:
            print(f"[Method 2] ✗ {e}")
            return False

    def read_frame(self):
        try:
            for chunk in self._iter:
                self._buffer += chunk
                start = self._buffer.find(self.JPEG_SOI)
                end   = self._buffer.find(self.JPEG_EOI, start + 2)
                if start != -1 and end != -1:
                    jpg          = self._buffer[start:end + 2]
                    self._buffer = self._buffer[end + 2:]
                    arr          = np.frombuffer(jpg, dtype=np.uint8)
                    frame        = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        return frame
        except Exception:
            return None
        return None

    def release(self):
        if self._resp:
            self._resp.close()


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 3: Snapshot polling (/capture on port 80)
# ─────────────────────────────────────────────────────────────────────────────
class SnapshotPoller:
    def __init__(self, base_url: str, timeout: int = 5):
        self.capture_url = base_url.rstrip("/") + "/capture"
        self.timeout     = timeout

    def connect(self) -> bool:
        print(f"[Method 3] Testing snapshot endpoint → {self.capture_url}")
        try:
            req  = urllib.request.Request(
                self.capture_url + f"?_cb={int(time.time()*1000)}",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            data = resp.read()
            if data[:2] == b'\xff\xd8':
                print("[Method 3] ✓ Snapshot endpoint works!")
                return True
            print("[Method 3] ✗ Response is not a JPEG.")
        except Exception as e:
            print(f"[Method 3] ✗ {e}")
        return False

    def read_frame(self):
        try:
            req  = urllib.request.Request(
                self.capture_url + f"?_cb={int(time.time()*1000)}",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            data = resp.read()
            arr  = np.frombuffer(data, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def release(self):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Pose utilities
# ─────────────────────────────────────────────────────────────────────────────
def calculate_angle(a, b, c):
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - np.arctan2(a[1]-b[1], a[0]-b[0])
    angle   = np.abs(radians * 180.0 / np.pi)
    if angle > 180.0:
        angle = 360 - angle
    return angle


def draw_pose(image, results, frame_w, frame_h):
    """Run landmark extraction, angle calc, and indicator drawing on one frame."""
    try:
        landmarks = results.pose_landmarks.landmark

        # ── Left arm angle ────────────────────────────────────────────────────
        shoulder = [landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].x,
                    landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].y]
        elbow    = [landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value].x,
                    landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value].y]
        wrist    = [landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value].x,
                    landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value].y]

        angle = calculate_angle(shoulder, elbow, wrist)
        elbow_px = tuple(np.multiply(elbow, [frame_w, frame_h]).astype(int))
        cv2.putText(image, str(int(angle)), elbow_px,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

        # ── Key-point indicators ──────────────────────────────────────────────
        def draw_indicator(landmark, label):
            pos = tuple(np.multiply([landmark.x, landmark.y],
                                    [frame_w, frame_h]).astype(int))
            cv2.circle(image, pos, 8, (0, 200, 0), -1)
            cv2.putText(image, label, (pos[0]+10, pos[1]+10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 205, 0), 1, cv2.LINE_AA)

        draw_indicator(landmarks[mp_pose.PoseLandmark.LEFT_INDEX.value],  "Left Hand")
        draw_indicator(landmarks[mp_pose.PoseLandmark.RIGHT_INDEX.value], "Right Hand")
        draw_indicator(landmarks[mp_pose.PoseLandmark.NOSE.value],        "Head")

    except Exception:
        pass

    # ── Skeleton overlay ──────────────────────────────────────────────────────
    mp_drawing.draw_landmarks(
        image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
        mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
        mp_drawing.DrawingSpec(color=(245,  66, 230), thickness=2, circle_radius=2),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Detector  (pose estimation edition)
# ─────────────────────────────────────────────────────────────────────────────
class Detector:

    ESP32_BASE       = "http://10.171.25.8"
    ESP32_STREAM_URL = "http://10.171.25.8:81/stream"

    def __init__(self, videoPath):
        self.videoPath = videoPath

    def onvideo(self):
        is_http = isinstance(self.videoPath, str) and self.videoPath.startswith("http")
        if is_http:
            self._run_esp32()
        else:
            self._run_opencv(self.videoPath)

    # ── Try all 3 connection methods ──────────────────────────────────────────
    def _run_esp32(self):
        print("\n" + "="*60)
        print("  Trying all connection methods for ESP32-CAM...")
        print("="*60 + "\n")

        cap = try_opencv_capture(self.ESP32_STREAM_URL)
        if cap:
            self._loop_opencv_cap(cap, "ESP32-CAM [OpenCV]")
            return

        rstream = RequestsStream(self.ESP32_STREAM_URL, timeout=15)
        if rstream.connect():
            self._loop_generic(rstream, "ESP32-CAM [requests]")
            return

        poller = SnapshotPoller(self.ESP32_BASE, timeout=5)
        if poller.connect():
            self._loop_generic(poller, "ESP32-CAM [snapshot]")
            return

        print("\n[ERROR] All 3 methods failed.")
        print(f"  • Try opening {self.ESP32_STREAM_URL} in your browser.")
        print(f"  • Try opening {self.ESP32_BASE}/capture in your browser.")
        print("  • Make sure 'Start Stream' was clicked in the ESP32 web UI.")
        print("  • Confirm your PC is on the same Wi-Fi as the ESP32.")

    # ── Generic frame loop (RequestsStream / SnapshotPoller) ─────────────────
    def _loop_generic(self, source, title: str):
        print(f"[Detector] Stream live ({title}) — press 'q' to quit.\n")
        prev_time  = time.time()
        fail_count = 0
        MAX_FAILS  = 30

        with mp_pose.Pose(min_detection_confidence=0.5,
                          min_tracking_confidence=0.5) as pose:
            while True:
                frame = source.read_frame()
                if frame is None:
                    fail_count += 1
                    if fail_count >= MAX_FAILS:
                        print("[ERROR] Too many frame failures — stopping.")
                        break
                    time.sleep(0.05)
                    continue

                fail_count = 0
                frame_h, frame_w = frame.shape[:2]

                now       = time.time()
                fps       = 1.0 / max(now - prev_time, 1e-6)
                prev_time = now

                # ── Pose inference ────────────────────────────────────────────
                image          = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image.flags.writeable = False
                results        = pose.process(image)
                image.flags.writeable = True
                image          = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

                draw_pose(image, results, frame_w, frame_h)

                cv2.putText(image, f"FPS: {fps:.1f}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow(title, image)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        source.release()
        cv2.destroyAllWindows()

    # ── OpenCV cap loop ───────────────────────────────────────────────────────
    def _loop_opencv_cap(self, cap, title: str):
        print(f"[Detector] Stream live ({title}) — press 'q' to quit.\n")
        prev_time = time.time()

        with mp_pose.Pose(min_detection_confidence=0.5,
                          min_tracking_confidence=0.5) as pose:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                frame_h, frame_w = frame.shape[:2]
                now       = time.time()
                fps       = 1.0 / max(now - prev_time, 1e-6)
                prev_time = now

                # ── Pose inference ────────────────────────────────────────────
                image          = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image.flags.writeable = False
                results        = pose.process(image)
                image.flags.writeable = True
                image          = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

                draw_pose(image, results, frame_w, frame_h)

                cv2.putText(image, f"FPS: {fps:.1f}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow(title, image)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        cap.release()
        cv2.destroyAllWindows()

    # ── Local webcam / video file ─────────────────────────────────────────────
    def _run_opencv(self, source):
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"[ERROR] Cannot open source: {source}")
            return
        self._loop_opencv_cap(cap, "Pose Estimation")