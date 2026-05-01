import cv2
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

np.random.seed(20)


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 1: OpenCV VideoCapture (simplest — works if OpenCV has FFMPEG built in)
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
# METHOD 2: requests library streaming (more robust than urllib for chunked HTTP)
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
            print("[Method 2] requests library not installed. Run: pip install requests")
            return False
        try:
            self._resp = requests.get(
                self.url,
                stream=True,
                timeout=self.timeout,
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
                    jpg   = self._buffer[start:end + 2]
                    self._buffer = self._buffer[end + 2:]
                    arr   = np.frombuffer(jpg, dtype=np.uint8)
                    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        return frame
        except Exception:
            return None
        return None

    def release(self):
        if self._resp:
            self._resp.close()


# ─────────────────────────────────────────────────────────────────────────────
# METHOD 3: Snapshot polling — hits /capture repeatedly (no stream needed)
# Works even when port 81 is unreachable; uses port 80 only.
# ─────────────────────────────────────────────────────────────────────────────
class SnapshotPoller:
    """
    Polls http://10.171.25.8/capture repeatedly.
    Slower (~5–10 FPS max) but very reliable — same port as the web UI.
    """
    def __init__(self, base_url: str, timeout: int = 5):
        self.capture_url = base_url.rstrip("/") + "/capture"
        self.timeout     = timeout
        self._ok         = False

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
                self._ok = True
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
# Detector
# ─────────────────────────────────────────────────────────────────────────────
class Detector:

    ESP32_BASE       = "http://10.171.25.8"
    ESP32_STREAM_URL = "http://10.171.25.8:81/stream"

    def __init__(self, videoPath, configPath, modelPath, classesPath):
        self.videoPath   = videoPath
        self.configPath  = configPath
        self.modelPath   = modelPath
        self.classesPath = classesPath

        self.net = cv2.dnn.DetectionModel(self.modelPath, self.configPath)
        self.net.setInputSize(320, 320)
        self.net.setInputScale(1.0 / 127.5)
        self.net.setInputMean((127.5, 127.5, 127.5))
        self.net.setInputSwapRB(True)

        self.readClasses()

    def readClasses(self):
        with open(self.classesPath, "r") as f:
            self.classesList = f.read().splitlines()
        self.classesList.insert(0, "__Background__")
        self.colorList = np.random.uniform(0, 255, size=(len(self.classesList), 3))

    def _draw_box(self, image, bbox, label, confidence, color):
        x, y, w, h = bbox
        text = f"{label}: {confidence:.2f}"
        cv2.rectangle(image, (x, y), (x + w, y + h), color, 1)
        (tw, th), bl = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(image, (x, y - th - bl - 4), (x + tw, y), color, -1)
        cv2.putText(image, text, (x, y - bl - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        tick = min(int(w * 0.2), int(h * 0.2), 20)
        for (cx, cy), (dx, dy) in [
            ((x,     y),     ( 1,  1)),
            ((x + w, y),     (-1,  1)),
            ((x,     y + h), ( 1, -1)),
            ((x + w, y + h), (-1, -1)),
        ]:
            cv2.line(image, (cx, cy), (cx + dx * tick, cy), color, 3)
            cv2.line(image, (cx, cy), (cx, cy + dy * tick), color, 3)

    def _detect_and_draw(self, frame):
        ids, confs, boxes = self.net.detect(frame, confThreshold=0.5)
        if len(boxes) == 0:
            return
        boxes   = list(boxes)
        confs   = list(map(float, np.array(confs).reshape(-1)))
        indices = cv2.dnn.NMSBoxes(boxes, confs, score_threshold=0.5, nms_threshold=0.3)
        for i in np.array(indices).flatten():
            self._draw_box(
                frame, boxes[i],
                self.classesList[int(ids[i])],
                confs[i],
                [int(c) for c in self.colorList[int(ids[i])]]
            )

    def onvideo(self):
        is_http = isinstance(self.videoPath, str) and self.videoPath.startswith("http")
        if is_http:
            self._run_esp32()
        else:
            self._run_opencv(self.videoPath)

    # ── Try all 3 methods in order ────────────────────────────────────────────
    def _run_esp32(self):
        print("\n" + "="*60)
        print("  Trying all connection methods for ESP32-CAM...")
        print("="*60 + "\n")

        # ── Method 1: OpenCV VideoCapture ─────────────────────────────────────
        cap = try_opencv_capture(self.ESP32_STREAM_URL)
        if cap:
            self._loop_opencv_cap(cap, "ESP32-CAM [OpenCV]")
            return

        # ── Method 2: requests streaming ─────────────────────────────────────
        rstream = RequestsStream(self.ESP32_STREAM_URL, timeout=15)
        if rstream.connect():
            self._loop_generic(rstream, "ESP32-CAM [requests]")
            return

        # ── Method 3: snapshot polling (/capture on port 80) ─────────────────
        poller = SnapshotPoller(self.ESP32_BASE, timeout=5)
        if poller.connect():
            self._loop_generic(poller, "ESP32-CAM [snapshot]")
            return

        print("\n[ERROR] All 3 methods failed. Things to try:")
        print(f"  • Open {self.ESP32_STREAM_URL} directly in your browser — does it show video?")
        print(f"  • Open {self.ESP32_BASE}/capture in your browser — does it show a photo?")
        print("  • Make sure you clicked 'Start Stream' in the ESP32 web UI.")
        print("  • Confirm your PC's Wi-Fi is the same network as the ESP32.")

    # ── Generic frame loop (works with RequestsStream and SnapshotPoller) ─────
    def _loop_generic(self, source, title: str):
        print(f"[Detector] Stream live ({title}) — press 'q' to quit.\n")
        prev_time  = time.time()
        fail_count = 0
        MAX_FAILS  = 30

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
            now        = time.time()
            fps        = 1.0 / max(now - prev_time, 1e-6)
            prev_time  = now

            self._detect_and_draw(frame)
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(title, frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        source.release()
        cv2.destroyAllWindows()

    # ── OpenCV cap loop ───────────────────────────────────────────────────────
    def _loop_opencv_cap(self, cap, title: str):
        print(f"[Detector] Stream live ({title}) — press 'q' to quit.\n")
        prev_time = time.time()

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            now       = time.time()
            fps       = 1.0 / max(now - prev_time, 1e-6)
            prev_time = now

            self._detect_and_draw(frame)
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(title, frame)

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
        self._loop_opencv_cap(cap, "Detection")