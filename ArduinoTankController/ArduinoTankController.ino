/** Hack Pack: Tank Plant
 * IMPROVED SERIAL HANDLING VERSION
 * Fixed serial communication issues with simplified, robust parsing
 */

#pragma region LICENSE
/*
MIT License

Copyright (c) 2025 CrunchLabs

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
#pragma endregion LICENSE

#pragma region LIBRARIES
#include <Adafruit_IS31FL3731.h>
#include <Arduino.h>
#include <CL_DRV8835.h>
#include <MatrixFace.h>
#include <Servo.h>
#include <elapsedMillis.h>
#pragma endregion LIBRARIES

#pragma region PIN DEFINITIONS
// motor control pins
constexpr int LEFT_SPEED_PIN = 6;
constexpr int LEFT_DIR_PIN = 7;
constexpr int RIGHT_SPEED_PIN = 5;
constexpr int RIGHT_DIR_PIN = 4;
constexpr int SERVO_PIN = 9;
#pragma endregion PIN DEFINITIONS

#pragma region CONFIGURATION

#define DEBUG_SERIAL 1
#if DEBUG_SERIAL
#define DEBUG_PRINT(x) Serial.print(x)
#define DEBUG_PRINTLN(x) Serial.println(x)
#else
#define DEBUG_PRINT(x)
#define DEBUG_PRINTLN(x)
#endif

// Motor reversal settings
#define REVERSE_RIGHT_MOTOR false
#define REVERSE_LEFT_MOTOR false

// Servo trim for centering the head
constexpr int8_t SERVO_TRIM = 0;

// Speeds for remote control movement
constexpr int16_t TANK_MOVE_SPEED = 220;
constexpr int16_t TANK_TURN_SPEED = 220;
#pragma endregion CONFIGURATION

#pragma region GLOBAL VARIABLES
// --- Hardware Objects ---
CL_DRV8835 tank(LEFT_SPEED_PIN, LEFT_DIR_PIN, RIGHT_SPEED_PIN, RIGHT_DIR_PIN);
Servo headServo;
Adafruit_IS31FL3731 matrix = Adafruit_IS31FL3731();
Face face(matrix);

// --- Remote Control State ---
bool keyW_pressed = false;
bool keyA_pressed = false;
bool keyS_pressed = false;
bool keyD_pressed = false;
bool keyQ_pressed = false;
bool keyE_pressed = false;

// --- Head Control ---
int currentServoPos = 90;
elapsedMillis headMoveTimer;
const unsigned int HEAD_MOVE_INTERVAL = 10;

// --- Simplified Serial Handling ---
unsigned long lastHeartbeat = 0;
#pragma endregion GLOBAL VARIABLES

#pragma region FUNCTION PROTOTYPES
void processSerialCommand();
void handleMovement();
void handleHeadControl();
void parseCommand(String command);
#pragma endregion FUNCTION PROTOTYPES

//********************************************************************************************************
// SETUP
//********************************************************************************************************
String serialBuffer = "";
void setup() {
  // Start serial
  Serial.begin(9600);  
  
  // --- Initialize Servo ---
  headServo.attach(SERVO_PIN);
  currentServoPos = 90 + SERVO_TRIM;
  headServo.write(currentServoPos);
  
  // --- Initialize LED Matrix ---
  if (matrix.begin()) {
    matrix.setRotation(0);
    face.storeImagesInFrames();
    face.setFaceState(FaceStates::EYES_FORWARD);
    face.updateFace();
  }
  
  // --- Initialize Motor Driver ---
  tank.rightMotorReversed = REVERSE_RIGHT_MOTOR;
  tank.leftMotorReversed = REVERSE_LEFT_MOTOR;
  tank.stop();
  
}


void loop() {
  // Heartbeat every 5 seconds (reduced frequency)
  // if (millis() - lastHeartbeat > 3000) {
  //   Serial.println("OK");
  //   lastHeartbeat = millis();
  // }
  
  // Process serial commands
  processSerialCommand();
  
  // Update movement and head control
  handleMovement();
  handleHeadControl();
  
  // Update face display
  // face.updateFace();
}

#pragma region FUNCTION DEFINITIONS

/**
 * @brief Parse and execute command
 * Expected format: "keydown:w" or "keyup:s"
 */
void parseCommand(String command) {
  command.trim();
  command.toLowerCase();
  
  if (command.length() < 7) return; // Minimum: "keyup:x"
  
  int colonPos = command.indexOf(':');
  if (colonPos == -1) return;
  
  String action = command.substring(0, colonPos);
  String key = command.substring(colonPos + 1);
  
  // Validate action
  bool isKeyDown;
  if (action == "keydown") {
    isKeyDown = true;
  } else if (action == "keyup") {
    isKeyDown = false;
  } else {
    return; // Invalid action
  }
  
  // Process key commands
  if (key.length() != 1) return; // Only single character keys
  
  char keyChar = key.charAt(0);
  
  switch (keyChar) {
    case 'w':
      keyW_pressed = isKeyDown;
      DEBUG_PRINTLN(isKeyDown ? "Forward ON" : "Forward OFF");
      break;
    case 'a':
      keyA_pressed = isKeyDown;
      DEBUG_PRINTLN(isKeyDown ? "Left ON" : "Left OFF");
      break;
    case 's':
      keyS_pressed = isKeyDown;
      DEBUG_PRINTLN(isKeyDown ? "Backward ON" : "Backward OFF");
      break;
    case 'd':
      keyD_pressed = isKeyDown;
      DEBUG_PRINTLN(isKeyDown ? "Right ON" : "Right OFF");
      break;
    case 'q':
      keyQ_pressed = isKeyDown;
      DEBUG_PRINTLN(isKeyDown ? "Head Left ON" : "Head Left OFF");
      break;
    case 'e':
      keyE_pressed = isKeyDown;
      DEBUG_PRINTLN(isKeyDown ? "Head Right ON" : "Head Right OFF");
      break;
    case 'r':
      if (isKeyDown) {
        face.setFaceState(FaceStates::SMILING_FACE);
        face.updateFace();
        DEBUG_PRINTLN("Face: SMILING");
      }
      break;
    case 't':
      if (isKeyDown) {
        face.setFaceState(FaceStates::ANGRY_FACE);
        face.updateFace();
        DEBUG_PRINTLN("Face: ANGRY");
      }
      break;
    case 'y':
      if (isKeyDown) {
        face.setFaceState(FaceStates::EYES_CONFUSED);
        face.updateFace();
        DEBUG_PRINTLN("Face: CONFUSED");
      }
      break;
    default:
      DEBUG_PRINT("Unknown key: ");
      DEBUG_PRINTLN(keyChar);
      break;
  }
}

void processSerialCommand() {
  // Read all available characters
  while (Serial.available() > 0) {
    char incomingByte = Serial.read();
    serialBuffer += incomingByte;
  }
  
  // Process complete commands (lines ending with \n)
  int newlinePos;
  while ((newlinePos = serialBuffer.indexOf('\n')) != -1) {
    // Extract the command
    String command = serialBuffer.substring(0, newlinePos);
    command.trim();
    
    // Remove processed command from buffer
    serialBuffer = serialBuffer.substring(newlinePos + 1);
    
    // Process the command if it's not empty
    if (command.length() > 0) {
      DEBUG_PRINT("Incoming command: ");
      DEBUG_PRINTLN(command);
      parseCommand(command);
    }
  }
}

/**
 * @brief Controls tank movement based on key states
 */
void handleMovement() {
  int16_t leftSpeed = 0;
  int16_t rightSpeed = 0;
  
  // Forward/backward
  if (keyW_pressed) {
    leftSpeed += TANK_MOVE_SPEED;
    rightSpeed += TANK_MOVE_SPEED;
  }
  if (keyS_pressed) {
    leftSpeed -= TANK_MOVE_SPEED;
    rightSpeed -= TANK_MOVE_SPEED;
  }
  
  // Turning
  if (keyA_pressed) {
    leftSpeed -= TANK_TURN_SPEED;
    rightSpeed += TANK_TURN_SPEED;
  }
  if (keyD_pressed) {
    leftSpeed += TANK_TURN_SPEED;
    rightSpeed -= TANK_TURN_SPEED;
  }
  
  // Apply constraints and set motor speeds
  leftSpeed = constrain(leftSpeed, -255, 255);
  rightSpeed = constrain(rightSpeed, -255, 255);
  tank.direct(leftSpeed, rightSpeed);
}

/**
 * @brief Controls head servo position
 */
void handleHeadControl() {
  if (headMoveTimer > HEAD_MOVE_INTERVAL) {
    bool moved = false;
    
    if (keyQ_pressed && currentServoPos > 0) {
      currentServoPos--;
      moved = true;
    }
    if (keyE_pressed && currentServoPos < 180) {
      currentServoPos++;
      moved = true;
    }
    
    if (moved) {
      headServo.write(currentServoPos);
    }
    
    headMoveTimer = 0;
  }
}

#pragma endregion FUNCTION DEFINITIONS