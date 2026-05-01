#include "esp_camera.h"
#include <WiFi.h>
#include <ESP32Servo.h>
#include "board_config.h"
// --- Configuration ---
//const char* ssid = "DESKTOP-AKCER 0611";
//const char* password = "12345678";

const char *ssid = "Wangaarey✨";
const char *password = "dyuwqcayqjd6cid";
Servo myServo;
int servoPin = 13; // Signal wire to GPIO 13

void setup() {
  Serial.begin(115200);
  myServo.attach(servoPin);
  myServo.write(90); // Start at center

  // Standard ESP32-CAM Camera Initialization (AI-Thinker Module)
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = 5; config.pin_d1 = 18; config.pin_d2 = 19; 
  config.pin_d3 = 21; config.pin_d4 = 36; config.pin_d5 = 39; 
  config.pin_d6 = 34; config.pin_d7 = 35; config.pin_xclk = 0;
  config.pin_pclk = 22; config.pin_vsync = 25; config.pin_href = 23;
  config.pin_sscb_sda = 26; config.pin_sscb_scl = 27; config.pin_pwdn = 32;
  config.pin_reset = -1;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA; 
  config.jpeg_quality = 12;
  config.fb_count = 1;
  config.xclk_freq_hz = 20000000;

  esp_err_t err = esp_camera_init(&config);
  
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); }
  Serial.println(WiFi.localIP()); // You'll need this IP for the Python script
}

void loop() {
  // Check for movement commands from the Laptop
  if (Serial.available() > 0) {
    String data = Serial.readStringUntil('\n');
    int angle = data.toInt();
    if (angle >= 0 && angle <= 180) {
      myServo.write(angle);
    }
  }
}