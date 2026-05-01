import cv2
import os

# 1. Connection Setup
# Replace with your ESP32's current IP address
url = "http://192.168.100.74:81/stream" 

# 2. File Path Setup
# This saves the file to your Windows "Videos" folder
save_path = os.path.join(os.path.expanduser("~"), "Videos", "esp32_project_record.mp4")

cap = cv2.VideoCapture(url)

# 3. Video Writer Setup (The MP4 configuration)
# 'mp4v' is the standard codec for .mp4 files in OpenCV
fourcc = cv2.VideoWriter_fourcc(*'mp4v') 

# We set it to 20 FPS and 640x480 (VGA)
out = cv2.VideoWriter(save_path, fourcc, 20.0, (640, 480))

if not cap.isOpened():
    print("Error: Cannot connect to ESP32. Check IP and close any browser tabs using the stream.")
    exit()

print(f"Recording to: {save_path}")
print("!!! IMPORTANT: Click the video window and press 'q' to save correctly !!!")

try:
    while True:
        ret, frame = cap.read()
        
        if not ret:
            print("Stream interrupted.")
            break

        # CRITICAL: This ensures every frame is exactly 640x480 for the MP4 file
        frame = cv2.resize(frame, (640, 480))

        # Write to file
        out.write(frame)

        # Show the live feed
        cv2.imshow('ESP32 Live Stream', frame)

        # Listen for the 'q' key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Saving and exiting...")
            break

finally:
    # 4. The "Seal" - This finalizes the MP4 header
    cap.release()
    out.release()
    cv2.destroyAllWindows()

    if os.path.exists(save_path):
        print(f"Done! Video saved successfully to: {save_path}")
    else:
        print("Error: File was not created. Check folder permissions.")