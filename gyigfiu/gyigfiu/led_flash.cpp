// led_flash.cpp
#include "Arduino.h"
#include "board_config.h"

#if defined(LED_GPIO_NUM)
void setupLedFlash() {
  pinMode(LED_GPIO_NUM, OUTPUT);
  digitalWrite(LED_GPIO_NUM, LOW); // OFF by default
}
#else
void setupLedFlash() {
  // No LED pin defined, do nothing
}
#endif