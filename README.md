<div align="center">

# 👁️ ESP32-CAM Security Vision
### Pose-Based Suspicious Activity Detection & Servo Tracking System

<br/>

[![Arduino](https://img.shields.io/badge/Arduino-ESP32-00979D?style=for-the-badge&logo=arduino&logoColor=white)](https://www.arduino.cc)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-DNN-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-Pose-FF6B35?style=for-the-badge&logo=google&logoColor=white)](https://mediapipe.dev)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)

<br/>

> **An ESP32-CAM streams live video over Wi-Fi. MediaPipe Pose detects people and analyses their body language in real time — flagging suspicious behaviour, sending email alerts with snapshots, and steering a physical servo motor to track the person across the frame.**

<br/>

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Hardware Architecture](#hardware-architecture)
  - [ESP32-CAM Pin Configuration](#esp32-cam-pin-configuration)
  - [Servo Wiring](#servo-wiring)
- [Getting Started](#getting-started)
  - [1. Flash the ESP32-CAM](#1-flash-the-esp32-cam)
  - [2. Run the Detector](#2-run-the-detector)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
  - [Email Alerts](#email-alerts)
  - [Servo Tuning](#servo-tuning)
  - [Camera Settings](#camera-settings)
- [Detected Activities](#detected-activities)
- [Notes & Troubleshooting](#notes--troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**ESP32-CAM Security Vision** turns an ESP32-CAM and a servo motor into a smart, auto-tracking security node. The board streams JPEG snapshots over your local Wi-Fi network. A Python host reads the stream, runs **MediaPipe Pose** to locate a person's full skeleton, and analyses joint positions to detect suspicious behaviours — raised hands, falling, crouching, loitering, and fast movement.

When a threat is detected, the system fires an **email alert with a snapshot attachment**. Meanwhile, a **ServoTracker** maps the person's horizontal position inside the frame to a servo angle and sends it to the ESP32 over HTTP — physically rotating the camera mount to keep the subject centred.

---

## Features

| Feature | Description |
|---|---|
| 📡 Wireless Snapshot Stream | JPEG snapshot polling from ESP32-CAM via `/capture` endpoint |
| 🦴 Full-Body Pose Estimation | MediaPipe Pose — 33 landmarks with visibility filtering |
| 🚨 Suspicious Activity Detection | Raised hands, falling, crouching, loitering, running |
| 📧 Email Alerts | SMTP email with JPEG snapshot attachment, per-activity cooldown |
| 🔁 Auto Servo Tracking | Person's X centroid → servo angle (0°–180°) via HTTP `/servo` |
| 📦 Smooth Bounding Box | Rolling average over landmark history reduces jitter |
| 🖥️ Live HUD Overlay | FPS counter, alert banner, servo angle, pose skeleton & joint angles |
| 📂 Local Source Support | Also works with a local webcam or video file |

---

## Tech Stack

### Firmware (ESP32-CAM)

| Technology | Purpose |
|---|---|
| [Arduino ESP32](https://docs.espressif.com/projects/arduino-esp32/) | Board support & camera driver |
| `esp_camera.h` | OV2640 camera init & JPEG frame capture |
| `ESP32Servo` | Servo PWM on GPIO 14 |
| `WiFi.h` | Wi-Fi station mode & HTTP server |
| `app_httpd.cpp` | `/capture` snapshot endpoint + `/servo?angle=` endpoint |

### Python Host

| Technology | Purpose |
|---|---|
| [Python 3.x](https://python.org) | Runtime |
| [MediaPipe `mp.solutions.pose`](https://mediapipe.dev) | 33-point body pose estimation |
| [OpenCV `cv2`](https://opencv.org) | Frame decode, drawing, display |
| [NumPy](https://numpy.org) | Landmark maths & smoothing |
| `smtplib` / `email` | SMTP email with image attachment |
| `urllib` / `requests` | Snapshot polling & servo HTTP commands |
| `threading` | Non-blocking email sends & servo requests |

---

## Hardware Architecture

```
┌─────────────────────────────────────────────────────┐
│                    ESP32-CAM                        │
│                                                     │
│  OV2640  ──► /capture  (JPEG snapshot)              │
│  Servo (GPIO 14) ◄── GET /servo?angle=<0-180>       │
│                                                     │
│  Wi-Fi ─────────────────────────────────────────── │
└─────────────────────────┬───────────────────────────┘
                          │ Local Network
                          ▼
          ┌────────────────────────────────────┐
          │         Python Host (PC)           │
          │                                    │
          │  SnapshotPoller → decode JPEG       │
          │  MediaPipe Pose → 33 landmarks      │
          │  PersonTracker  → smooth bbox       │
          │  ActivityDetector → classify pose  │
          │  ServoTracker   → send angle        │
          │  AlertManager   → email + snapshot  │
          │  OpenCV HUD     → display           │
          └────────────────────────────────────┘
```

---

### ESP32-CAM Pin Configuration

| GPIO | Function | Notes |
|---|---|---|
| GPIO 14 | Servo Signal | PWM via ESP32Servo — centres at 90° on boot |
| GPIO 4 | Onboard Flash LED | Optional — `setupLedFlash()` |
| CAMERA pins | OV2640 Camera | Defined in `board_config.h` |

---

### Servo Wiring

| Servo Wire | Connect To |
|---|---|
| Signal (Orange / Yellow) | GPIO 14 |
| VCC (Red) | 5 V external supply |
| GND (Brown / Black) | GND (shared with ESP32) |

> ⚠️ Power the servo from an external 5 V rail. Drawing servo current from the ESP32 causes brownouts during camera streaming.

---

## Getting Started

### Prerequisites

**Firmware:**
- Arduino IDE 2.x with ESP32 board package
- Libraries: `ESP32Servo` (install via Library Manager)

**Python:**
```bash
pip install opencv-python mediapipe numpy requests
```

---

### 1. Flash the ESP32-CAM

1. Open `CameraWebServer/FinalCameraWebServer/FinalCameraWebServer.ino` in Arduino IDE.
2. Set your Wi-Fi credentials:
   ```cpp
   const char *ssid     = "YOUR_SSID";
   const char *password = "YOUR_PASSWORD";
   ```
3. Select board: **AI Thinker ESP32-CAM**.
4. Upload and open Serial Monitor at **115200 baud**.
5. Note the IP address printed after `Camera Ready! Use 'http://`.

---

### 2. Run the Detector

Edit `Detector_esp32.py` and set your ESP32 IP:

```python
ESP32_BASE = "http://192.168.x.x"   # ← your ESP32-CAM's local IP
```

Then run:

```bash
python Detector_esp32.py
```

Press **`q`** to quit. The servo returns to 90° (centre) on exit.

---

## Project Structure

```
ESP32-CAM-Security-Vision/
│
├── CameraWebServer/
│   └── FinalCameraWebServer/
│       ├── FinalCameraWebServer.ino   # Arduino sketch — camera + servo server
│       ├── app_httpd.cpp              # /capture and /servo HTTP endpoints
│       └── board_config.h             # GPIO pin definitions
│
├── Detector_esp32.py                  # Full detection pipeline (main file)
└── README.md
```

---

## Configuration

### Email Alerts

Edit the `EMAIL_CONFIG` dict at the top of `Detector_esp32.py`:

```python
EMAIL_CONFIG = {
    "sender_email"    : "youremail@gmail.com",
    "sender_password" : "your_app_password_here",   # Gmail App Password
    "receiver_email"  : "security@example.com",
    "smtp_host"       : "smtp.gmail.com",
    "smtp_port"       : 587,
    "cooldown_seconds": 60,   # minimum gap between alerts for the same activity
}
```

> Use a **Gmail App Password** (not your account password). Generate one at Google Account → Security → App Passwords.

---

### Servo Tuning

Adjust class constants in `ServoTracker` inside `Detector_esp32.py`:

| Constant | Default | Description |
|---|---|---|
| `ANGLE_MIN` | `30` | Leftmost servo position (degrees) |
| `ANGLE_MAX` | `150` | Rightmost servo position (degrees) |
| `DEADBAND` | `0.04` | Fraction of frame width — ignore small movements |
| `MIN_DELTA_DEG` | `3` | Minimum angle change before sending an HTTP request |
| `SMOOTH` | `6` | Number of recent centroids averaged for smoothing |

> Swap `ANGLE_MIN` and `ANGLE_MAX` if the servo tracks in the wrong direction.

---

### Camera Settings

Configured in the Arduino sketch (`FinalCameraWebServer.ino`):

```cpp
config.frame_size   = FRAMESIZE_VGA;   // Resolution
config.jpeg_quality = 10;              // Lower = higher quality (0–63)
config.fb_count     = 2;               // Requires PSRAM
```

---

## Detected Activities

The `SuspiciousActivityDetector` class analyses MediaPipe landmarks each frame:

| Activity | Detection Logic |
|---|---|
| **Raised Hands** | Both wrists above the nose landmark |
| **Person Falling** | Nose Y-position below hip Y-position |
| **Crouching** | Knee landmark above hip landmark (inverted Y axis) |
| **Loitering** | Person stationary for more than 10 seconds |
| **Running / Fast Movement** | Centroid displacement speed exceeds threshold |

When any activity is detected:
- The bounding box turns **red**
- The activity label is shown in the **HUD banner**
- An **email alert** is fired (subject to the cooldown timer)

---

## Notes & Troubleshooting

**Snapshot not connecting?**
- Open `http://<ESP32_IP>/capture` in your browser — you should see a JPEG image.
- Make sure your PC and ESP32-CAM are on the same Wi-Fi network.
- Check Serial Monitor for the assigned IP address.

**Servo not responding?**
- Test directly: `http://<ESP32_IP>/servo?angle=45` in your browser.
- Confirm GPIO 14 is wired to the servo signal pin.
- Use an external 5 V power supply for the servo.

**Pose not detected?**
- Ensure the person is fully or mostly visible in the frame.
- Improve lighting — MediaPipe Pose requires reasonable contrast.
- Lower `min_detection_confidence` in the `mp_pose.Pose()` call if needed.

**Email not sending?**
- Use a Gmail **App Password**, not your regular password.
- Make sure 2-Step Verification is enabled on your Google account first.

---

## Contributing

Pull requests and suggestions are welcome. Open an issue first to discuss major changes.

1. Fork the repository
2. Create your branch: `git checkout -b feature/my-feature`
3. Commit: `git commit -m 'Add my feature'`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

Built for makers who want intelligence at the edge.

**ESP32-CAM Security Vision** — Detect. Track. Alert.

</div>