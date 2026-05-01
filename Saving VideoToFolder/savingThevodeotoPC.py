import cv2
import os

# Replace with your ESP32-CAM stream URL
url= "http://192.168.100.74:81/stream"

# Save path (Windows Videos folder)
save_path = os.path.join(os.path.expanduser("~"), "Videos", "esp32cam_record.avi")

cap = cv2.VideoCapture(url)

# Get frame size
frame_width = int(cap.get(3))
frame_height = int(cap.get(4))

# Define codec
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('esp32_capture.mp4', fourcc, 20.0, (640, 480))
print("Recording... Press 'q' to stop")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    out.write(frame)
    cv2.imshow('ESP32 Stream', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
out.release()
cv2.destroyAllWindows()

print(f"Saved to: {save_path}")