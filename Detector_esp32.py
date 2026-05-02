import cv2
import mediapipe as mp
import numpy as np
import time
import urllib.request
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
from collections import deque

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

mp_drawing = mp.solutions.drawing_utils
mp_pose    = mp.solutions.pose


# ═════════════════════════════════════════════════════════════════════════════
#  EMAIL CONFIG  ←  fill these in
# ═════════════════════════════════════════════════════════════════════════════
EMAIL_CONFIG = {
    "sender_email"    : "youremail@gmail.com",
    "sender_password" : "your_app_password_here",
    "receiver_email"  : "security@example.com",
    "smtp_host"       : "smtp.gmail.com",
    "smtp_port"       : 587,
    "cooldown_seconds": 60,
}


# ═════════════════════════════════════════════════════════════════════════════
#  SERVO TRACKER  — maps person X centroid to a servo angle and sends it
#  over WiFi to the ESP32 /servo endpoint (non-blocking, fire-and-forget)
# ═════════════════════════════════════════════════════════════════════════════
class ServoTracker:
    """
    Converts the horizontal position of the detected person inside the frame
    into a servo angle (0°–180°) and sends it to the ESP32 via HTTP.

    Tuning knobs
    ────────────
    ANGLE_MIN / ANGLE_MAX  : physical travel limits of your servo mount.
                             90° = dead centre. Swap MIN/MAX if the servo
                             moves in the wrong direction.
    DEADBAND               : fraction of frame width — ignore movements
                             smaller than this to avoid constant jitter.
    MIN_DELTA_DEG          : minimum angle change before a new request is
                             sent, avoids flooding the ESP32.
    SMOOTH                 : how many recent centroids to average together.
    """

    ANGLE_MIN     = 30      # leftmost servo position  (degrees)
    ANGLE_MAX     = 150     # rightmost servo position (degrees)
    DEADBAND      = 0.04    # fraction of frame width  (4%)
    MIN_DELTA_DEG = 3       # degrees — skip if change is smaller than this
    SMOOTH        = 6       # centroid history length for smoothing

    def __init__(self, esp32_base: str):
        self._base         = esp32_base.rstrip("/")
        self._servo_url    = f"{self._base}/servo"
        self._last_angle   = 90          # start centred
        self._cx_history   = deque(maxlen=self.SMOOTH)
        self._lock         = threading.Lock()

    # ── public API ────────────────────────────────────────────────────────────
    def update(self, box, frame_w: int):
        """
        Call once per frame with the current bounding box (x,y,w,h) and
        the frame width.  Sends a servo command if the person has moved
        enough to warrant it.  Returns the target angle (int) or None if
        no command was sent.
        """
        if box is None:
            return None

        # centroid X as a fraction of frame width  (0.0 = left, 1.0 = right)
        cx_frac = (box[0] + box[2] / 2.0) / max(frame_w, 1)

        with self._lock:
            self._cx_history.append(cx_frac)
            smooth_cx = float(np.mean(self._cx_history))

        # map 0.0→1.0 to ANGLE_MAX→ANGLE_MIN
        # (person on the left  → servo turns right, i.e. higher angle)
        # (person on the right → servo turns left,  i.e. lower angle)
        target = self.ANGLE_MAX + (self.ANGLE_MIN - self.ANGLE_MAX) * smooth_cx
        target = int(np.clip(target, self.ANGLE_MIN, self.ANGLE_MAX))

        # skip if change is within deadband
        if abs(cx_frac - 0.5) < self.DEADBAND / 2:
            return None

        # skip if angle hasn't changed enough
        if abs(target - self._last_angle) < self.MIN_DELTA_DEG:
            return None

        self._last_angle = target
        self._send_angle(target)
        return target

    def centre(self):
        """Return servo to 90° — call on shutdown or person lost."""
        self._last_angle = 90
        self._send_angle(90)

    # ── internal ──────────────────────────────────────────────────────────────
    def _send_angle(self, angle: int):
        """Fire-and-forget HTTP GET in a daemon thread."""
        t = threading.Thread(
            target=self._do_request, args=(angle,), daemon=True
        )
        t.start()

    def _do_request(self, angle: int):
        url = f"{self._servo_url}?angle={angle}"
        try:
            if HAS_REQUESTS:
                requests.get(url, timeout=1)
            else:
                urllib.request.urlopen(url, timeout=1)
        except Exception:
            pass   # best-effort; a missed frame is not critical


# ─────────────────────────────────────────────────────────────────────────────
# SNAPSHOT POLLING  (only streaming method)
# ─────────────────────────────────────────────────────────────────────────────
class SnapshotPoller:
    def __init__(self, base_url: str, timeout: int = 5):
        self.capture_url = base_url.rstrip("/") + "/capture"
        self.timeout     = timeout

    def connect(self) -> bool:
        print(f"[SnapshotPoller] Testing → {self.capture_url}")
        try:
            req  = urllib.request.Request(
                self.capture_url + f"?_cb={int(time.time()*1000)}",
                headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            if resp.read()[:2] == b'\xff\xd8':
                print("[SnapshotPoller] ✓ Snapshot works!")
                return True
        except Exception as e:
            print(f"[SnapshotPoller] ✗ {e}")
        return False

    def read_frame(self):
        try:
            req  = urllib.request.Request(
                self.capture_url + f"?_cb={int(time.time()*1000)}",
                headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            arr  = np.frombuffer(resp.read(), dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def release(self):
        pass


# ═════════════════════════════════════════════════════════════════════════════
#  ALERT MANAGER  — email with snapshot, runs in background thread
# ═════════════════════════════════════════════════════════════════════════════
class AlertManager:
    def __init__(self, config: dict):
        self.config     = config
        self._last_sent = {}
        self._lock      = threading.Lock()

    def _can_send(self, activity: str) -> bool:
        with self._lock:
            last = self._last_sent.get(activity, 0)
            if time.time() - last >= self.config["cooldown_seconds"]:
                self._last_sent[activity] = time.time()
                return True
        return False

    def send_alert(self, activity: str, frame: np.ndarray):
        if not self._can_send(activity):
            return
        snapshot = frame.copy()
        t = threading.Thread(
            target=self._send_email, args=(activity, snapshot), daemon=True
        )
        t.start()

    def _send_email(self, activity: str, frame: np.ndarray):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cfg       = self.config

            msg = MIMEMultipart()
            msg["From"]    = cfg["sender_email"]
            msg["To"]      = cfg["receiver_email"]
            msg["Subject"] = f"🚨 Security Alert: {activity} detected"

            body = (
                f"<h2 style='color:red;'>⚠ Suspicious Activity Detected</h2>"
                f"<p><b>Activity :</b> {activity}</p>"
                f"<p><b>Time&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;:</b> {timestamp}</p>"
                f"<p><b>Camera&nbsp;&nbsp;:</b> ESP32-CAM Security Feed</p>"
                f"<p>A snapshot is attached below.</p>"
            )
            msg.attach(MIMEText(body, "html"))

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            img_attachment = MIMEImage(buf.tobytes(), _subtype="jpeg")
            img_attachment["Content-Disposition"] = (
                f'attachment; filename="alert_{timestamp.replace(":","").replace(" ","_")}.jpg"'
            )
            msg.attach(img_attachment)

            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
                server.ehlo()
                server.starttls()
                server.login(cfg["sender_email"], cfg["sender_password"])
                server.sendmail(
                    cfg["sender_email"], cfg["receiver_email"], msg.as_string()
                )

            print(f"[Alert] ✓ Email sent — {activity} @ {timestamp}")

        except Exception as e:
            print(f"[Alert] ✗ Email failed: {e}")


# ═════════════════════════════════════════════════════════════════════════════
#  PERSON TRACKER  — bounding box from pose landmarks
# ═════════════════════════════════════════════════════════════════════════════
class PersonTracker:
    def __init__(self, smooth: int = 5):
        self._history = deque(maxlen=smooth)

    def update(self, landmarks, frame_w: int, frame_h: int):
        xs = [lm.x for lm in landmarks if lm.visibility > 0.3]
        ys = [lm.y for lm in landmarks if lm.visibility > 0.3]
        if not xs:
            return None

        pad  = 0.05
        xmin = max(0.0, min(xs) - pad)
        ymin = max(0.0, min(ys) - pad)
        xmax = min(1.0, max(xs) + pad)
        ymax = min(1.0, max(ys) + pad)

        box = (
            int(xmin * frame_w),
            int(ymin * frame_h),
            int((xmax - xmin) * frame_w),
            int((ymax - ymin) * frame_h),
        )
        self._history.append(box)

        xs_ = [b[0] for b in self._history]
        ys_ = [b[1] for b in self._history]
        ws_ = [b[2] for b in self._history]
        hs_ = [b[3] for b in self._history]
        return (
            int(np.mean(xs_)), int(np.mean(ys_)),
            int(np.mean(ws_)), int(np.mean(hs_))
        )

    @staticmethod
    def draw(image, box, color=(0, 255, 255), label="Person"):
        if box is None:
            return
        x, y, w, h = box
        cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
        tick = min(w // 5, h // 5, 25)
        for (cx, cy), (dx, dy) in [
            ((x,     y),     ( 1,  1)),
            ((x+w,   y),     (-1,  1)),
            ((x,     y+h),   ( 1, -1)),
            ((x+w,   y+h),   (-1, -1)),
        ]:
            cv2.line(image, (cx, cy), (cx + dx*tick, cy), color, 3)
            cv2.line(image, (cx, cy), (cx, cy + dy*tick), color, 3)

        cv2.putText(image, label, (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


# ═════════════════════════════════════════════════════════════════════════════
#  SUSPICIOUS ACTIVITY DETECTOR
# ═════════════════════════════════════════════════════════════════════════════
class SuspiciousActivityDetector:
    LOITER_SEC  = 10.0
    RUN_THRESH  = 0.08

    def __init__(self):
        self._loiter_start  = None
        self._prev_centroid = None
        self._prev_time     = time.time()

    def check(self, landmarks, box) -> list:
        alerts = []
        lm     = landmarks

        def y(part): return lm[part.value].y
        def vis(part): return lm[part.value].visibility

        PL = mp_pose.PoseLandmark

        # 1. Raised hands
        if vis(PL.LEFT_WRIST) > 0.4 and vis(PL.RIGHT_WRIST) > 0.4:
            if y(PL.LEFT_WRIST) < y(PL.NOSE) and y(PL.RIGHT_WRIST) < y(PL.NOSE):
                alerts.append("Raised Hands")

        # 2. Falling down
        if vis(PL.NOSE) > 0.4 and vis(PL.LEFT_HIP) > 0.4:
            if y(PL.NOSE) > y(PL.LEFT_HIP):
                alerts.append("Person Falling")

        # 3. Crouching
        if vis(PL.LEFT_KNEE) > 0.4 and vis(PL.LEFT_HIP) > 0.4:
            if y(PL.LEFT_KNEE) < y(PL.LEFT_HIP) - 0.05:
                alerts.append("Crouching")

        # 4 & 5. Loitering / Running
        if box is not None:
            cx  = box[0] + box[2] / 2
            cy  = box[1] + box[3] / 2
            now = time.time()

            if self._prev_centroid is not None:
                dist  = np.hypot(cx - self._prev_centroid[0],
                                 cy - self._prev_centroid[1])
                speed = dist / (box[2] + 1e-6)

                if speed > self.RUN_THRESH:
                    alerts.append("Running / Fast Movement")
                    self._loiter_start = None
                else:
                    if self._loiter_start is None:
                        self._loiter_start = now
                    elif now - self._loiter_start > self.LOITER_SEC:
                        alerts.append("Loitering")

            self._prev_centroid = (cx, cy)
            self._prev_time     = now

        return alerts


# ═════════════════════════════════════════════════════════════════════════════
#  POSE UTILITIES
# ═════════════════════════════════════════════════════════════════════════════
def calculate_angle(a, b, c):
    a, b, c  = np.array(a), np.array(b), np.array(c)
    radians  = (np.arctan2(c[1]-b[1], c[0]-b[0])
                - np.arctan2(a[1]-b[1], a[0]-b[0]))
    angle    = np.abs(radians * 180.0 / np.pi)
    return 360 - angle if angle > 180.0 else angle


def draw_pose_overlay(image, results, frame_w, frame_h):
    try:
        lm = results.pose_landmarks.landmark
        PL = mp_pose.PoseLandmark

        shoulder = [lm[PL.LEFT_SHOULDER.value].x, lm[PL.LEFT_SHOULDER.value].y]
        elbow    = [lm[PL.LEFT_ELBOW.value].x,    lm[PL.LEFT_ELBOW.value].y]
        wrist    = [lm[PL.LEFT_WRIST.value].x,    lm[PL.LEFT_WRIST.value].y]
        angle    = calculate_angle(shoulder, elbow, wrist)
        elbow_px = tuple(np.multiply(elbow, [frame_w, frame_h]).astype(int))
        cv2.putText(image, str(int(angle)), elbow_px,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

        def draw_indicator(landmark, label):
            pos = tuple(np.multiply(
                [landmark.x, landmark.y], [frame_w, frame_h]
            ).astype(int))
            cv2.circle(image, pos, 8, (0, 200, 0), -1)
            cv2.putText(image, label, (pos[0]+10, pos[1]+10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 205, 0), 1, cv2.LINE_AA)

        draw_indicator(lm[PL.LEFT_INDEX.value],  "L.Hand")
        draw_indicator(lm[PL.RIGHT_INDEX.value], "R.Hand")
        draw_indicator(lm[PL.NOSE.value],        "Head")

    except Exception:
        pass

    mp_drawing.draw_landmarks(
        image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
        mp_drawing.DrawingSpec(color=(245, 117,  66), thickness=2, circle_radius=2),
        mp_drawing.DrawingSpec(color=(245,  66, 230), thickness=2, circle_radius=2),
    )


def draw_alerts_hud(image, alerts: list):
    if not alerts:
        return
    overlay = image.copy()
    cv2.rectangle(overlay, (0, 0),
                  (image.shape[1], 36 + 28*len(alerts)), (0, 0, 180), -1)
    cv2.addWeighted(overlay, 0.55, image, 0.45, 0, image)
    cv2.putText(image, "SUSPICIOUS ACTIVITY", (10, 25),
                cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 200, 255), 2)
    for i, a in enumerate(alerts):
        cv2.putText(image, f"  . {a}", (10, 52 + i*28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)


def draw_servo_hud(image, angle):
    """Small HUD in the bottom-right showing the current servo angle."""
    if angle is None:
        return
    h, w = image.shape[:2]
    label = f"Servo: {angle}deg"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    x = w - tw - 14
    y = h - 12
    cv2.rectangle(image, (x - 4, y - th - 4), (w - 6, y + 4),
                  (30, 30, 30), -1)
    cv2.putText(image, label, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1, cv2.LINE_AA)


# ═════════════════════════════════════════════════════════════════════════════
#  DETECTOR  (main class)
# ═════════════════════════════════════════════════════════════════════════════
class Detector:

    ESP32_BASE = "http://192.168.43.8"

    def __init__(self, videoPath):
        self.videoPath   = videoPath
        self.alert_mgr   = AlertManager(EMAIL_CONFIG)
        self.tracker     = PersonTracker(smooth=5)
        self.activity    = SuspiciousActivityDetector()
        self.servo       = ServoTracker(self.ESP32_BASE)
        self._last_angle = None   # for the HUD display

    def onvideo(self):
        if isinstance(self.videoPath, str) and self.videoPath.startswith("http"):
            self._run_esp32()
        else:
            self._run_opencv(self.videoPath)

    # ── ESP32: snapshot polling ───────────────────────────────────────────────
    def _run_esp32(self):
        print("\n" + "="*60)
        print("  Connecting to ESP32-CAM Security Feed...")
        print("="*60 + "\n")

        poller = SnapshotPoller(self.ESP32_BASE, timeout=5)
        if poller.connect():
            self._loop_generic(poller, "Security Feed [snapshot]")
        else:
            print("\n[ERROR] Snapshot polling failed — check ESP32_BASE URL.")

    # ── Core per-frame logic ──────────────────────────────────────────────────
    def _process_frame(self, frame, pose):
        h, w = frame.shape[:2]

        image                 = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image.flags.writeable = False
        results               = pose.process(image)
        image.flags.writeable = True
        image                 = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        box    = None
        alerts = []

        if results.pose_landmarks:
            lm  = results.pose_landmarks.landmark
            box = self.tracker.update(lm, w, h)

            alerts = self.activity.check(lm, box)

            # ── Servo tracking ────────────────────────────────────────────────
            angle = self.servo.update(box, w)
            if angle is not None:
                self._last_angle = angle
            # ─────────────────────────────────────────────────────────────────

            box_color = (0, 0, 255) if alerts else (0, 255, 255)
            box_label = " | ".join(alerts) if alerts else "Person"
            PersonTracker.draw(image, box, color=box_color, label=box_label)

            draw_pose_overlay(image, results, w, h)
        else:
            # Person lost — servo returns to centre
            if self._last_angle is not None:
                self.servo.centre()
                self._last_angle = None

        draw_alerts_hud(image, alerts)
        draw_servo_hud(image, self._last_angle)

        for act in alerts:
            self.alert_mgr.send_alert(act, image)

        return image, alerts

    # ── Generic loop (snapshot) ───────────────────────────────────────────────
    def _loop_generic(self, source, title: str):
        print(f"[Detector] Live ({title}) — press 'q' to quit.\n")
        prev_time  = time.time()
        fail_count = 0

        with mp_pose.Pose(min_detection_confidence=0.5,
                          min_tracking_confidence=0.5) as pose:
            while True:
                frame = source.read_frame()
                if frame is None:
                    fail_count += 1
                    if fail_count >= 30:
                        print("[ERROR] Too many failures — stopping.")
                        break
                    time.sleep(0.05)
                    continue
                fail_count = 0

                now       = time.time()
                fps       = 1.0 / max(now - prev_time, 1e-6)
                prev_time = now

                image, _ = self._process_frame(frame, pose)

                cv2.putText(image, f"FPS: {fps:.1f}",
                            (10, image.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow(title, image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        self.servo.centre()
        source.release()
        cv2.destroyAllWindows()

    # ── Local file / webcam ───────────────────────────────────────────────────
    def _run_opencv(self, source):
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"[ERROR] Cannot open: {source}")
            return

        print(f"[Detector] Local source — press 'q' to quit.\n")
        prev_time = time.time()

        with mp_pose.Pose(min_detection_confidence=0.5,
                          min_tracking_confidence=0.5) as pose:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                now       = time.time()
                fps       = 1.0 / max(now - prev_time, 1e-6)
                prev_time = now

                image, _ = self._process_frame(frame, pose)

                cv2.putText(image, f"FPS: {fps:.1f}",
                            (10, image.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow("Security Feed", image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        self.servo.centre()
        cap.release()
        cv2.destroyAllWindows()