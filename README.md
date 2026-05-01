
# ESP32-CAM Real-Time Object Detection (CPU, OpenCV)



## 📌 Overview

This project enables real-time object detection using an ESP32-CAM as a wireless video source and OpenCV's DNN module for inference on a standard CPU (no GPU required). It is ideal for embedded, IoT, and low-power applications.

## 🚀 Features

- **ESP32-CAM integration**: Stream video from ESP32-CAM over Wi-Fi
- **CPU-only inference**: No GPU required, runs on laptops/desktops
- **OpenCV DNN**: Uses SSD MobileNet v3 (COCO dataset)
- **Multiple connection methods**: Robust ESP32-CAM connection (stream, HTTP, snapshot)
- **Webcam/video support**: Also works with local webcam or video files
- **Easy video saving**: Save ESP32-CAM streams to disk

## 🛠️ Installation

### Prerequisites

- Python 3.x
- OpenCV (`opencv-python`)
- NumPy

Install dependencies:

```bash
pip install opencv-python numpy
```

## 📂 Project Structure

- `main_esp32.py` — Main entry point for detection (choose ESP32/webcam/video)
- `Detector_esp32.py` — Handles ESP32-CAM connection and object detection
- `model_data/` — Contains model files:
	- `ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt`
	- `frozen_inference_graph.pb`
	- `coco.names`
- `Saving VideoToFolder/savingThevodeotoPC.py` — Save ESP32 stream to video file
- `CameraWebServer/` — ESP32 Arduino firmware (see `FinalCameraWebServer.ino`)

## 🔍 Usage

### 1️⃣ Flash ESP32-CAM

Upload the Arduino sketch in `CameraWebServer/FinalCameraWebServer/FinalCameraWebServer.ino` to your ESP32-CAM. Set your Wi-Fi SSID and password in the code.

### 2️⃣ Run Detection (Python)

By default, `main_esp32.py` will try to connect to the ESP32-CAM stream. You can also set `INPUT_SOURCE` to `webcam` or `video`.

```bash
python main_esp32.py
```

### 3️⃣ Save ESP32 Video to File

```bash
python Saving VideoToFolder/savingThevodeotoPC.py
```

## ⚙️ Configuration

- Edit `main_esp32.py` to set your ESP32-CAM IP address if needed.
- Place your test videos in `test_videos/`.

## 📝 Notes

- Make sure your PC and ESP32-CAM are on the same Wi-Fi network.
- If the stream fails, try opening the ESP32-CAM stream URL in your browser to debug.

## 🤝 Contributing

Pull requests and suggestions are welcome!

## 📜 License

This project is licensed under the **MIT License**.
