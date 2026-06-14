#include "I2Cdev.h"
#include "MPU6050.h"
#include "Wire.h"
#include "Adafruit_NeoPixel.h"
#include "BluetoothSerial.h"
#include <ESP32Servo.h>
#include <math.h>
#include <ctype.h>

#ifndef OUTPUT_OPEN_DRAIN
#define OUTPUT_OPEN_DRAIN OUTPUT
#endif

#ifndef RAD_TO_DEG
#define RAD_TO_DEG 57.2957795131f
#endif

// Pin settings
#define CHECK_LED     5
#define LED_PIN      15
#define NUMPIXELS    16
#define MPU_INT_PIN   4
#define MOTOR_X_PIN  27
#define MOTOR_Y_PIN  14
#define MOTOR_Z_PIN  12
#define AXIS_COUNT    3
#define AXIS_X        0
#define AXIS_Y        1
#define AXIS_Z        2
#define I2C_SDA_PIN  21
#define I2C_SCL_PIN  22
#define MPU_ADDR   0x68

// ESC settings
#define ESC_MIN_US    1000
#define ESC_MAX_US    2000
#define ESC_NEUTRAL     90
#define ESC_MIN_ANGLE    0
#define ESC_MAX_ANGLE  180

// Balancing PID settings
#define PID_LOOP_MS             20
#define BALANCE_OUTPUT_LIMIT    30.0f
#define BALANCE_INTEGRAL_LIMIT  80.0f
#define BALANCE_FALL_ANGLE      45.0f
#define COMPLEMENTARY_ALPHA      0.98f
#define MOTOR_DEADBAND           2
#define RUN_BOOT_CALIBRATION      0
#define BT_RETRY_MS           5000
#define BT_RFCOMM_CHANNEL        1

Adafruit_NeoPixel strip(NUMPIXELS, LED_PIN, NEO_GRB + NEO_KHZ800);
BluetoothSerial SerialBT;
MPU6050 accelgyro;
Servo motorESC[AXIS_COUNT];
const int motorPins[AXIS_COUNT] = {MOTOR_X_PIN, MOTOR_Y_PIN, MOTOR_Z_PIN};
const char axisNames[AXIS_COUNT] = {'X', 'Y', 'Z'};
int motorDirection[AXIS_COUNT] = {1, 1, 1};

struct SensorData {
    int16_t ax, ay, az, gx, gy, gz;
};

struct PidState {
    float k1;
    float k2;
    float k3;
    float setpointDeg[AXIS_COUNT];
    float currentDeg[AXIS_COUNT];
    float angleOffsetDeg[AXIS_COUNT];
    float gyroRateDps[AXIS_COUNT];
    float pidOutput[AXIS_COUNT];
    float motorSpeedX;
    float motorSpeedY;
    float gyroYfilt;
    float gyroZfilt;
    float outputLimitDeg;
    float minOutputDeg;
    bool autoMode;
    bool fault;
    bool motorEnabled[AXIS_COUNT];
    int manualEscAngle[AXIS_COUNT];
    int escAngle[AXIS_COUNT];
};

SemaphoreHandle_t ledMutex;
SemaphoreHandle_t sensorMutex;
SemaphoreHandle_t pidMutex;

volatile bool mpuInterrupt = false;
bool mpuReady = false;
bool bluetoothReady = false;
bool bluetoothConnected = false;
const char *btDeviceName = "ESP32-Cube-blue";
SensorData currentData = {0, 0, 0, 0, 0, 0};
PidState motorPid = {
    12.0f,  // K1: angle gain
    1.2f,   // K2: gyro gain
    0.0f,   // K3: estimated wheel speed gain
    {0.0f, 0.0f, 0.0f},  // target angles: X, Y, Z
    {0.0f, 0.0f, 0.0f},  // estimated angles: X, Y, Z
    {0.0f, 0.0f, 0.0f},  // zero offsets: X, Y, Z
    {0.0f, 0.0f, 0.0f},  // gyro rates: X, Y, Z
    {0.0f, 0.0f, 0.0f},  // PID outputs
    0.0f,
    0.0f,
    0.0f,
    0.0f,
    BALANCE_OUTPUT_LIMIT,
    0.0f,
    false,  // start in manual mode
    false,
    {true, true, true},
    {ESC_NEUTRAL, ESC_NEUTRAL, ESC_NEUTRAL},
    {ESC_NEUTRAL, ESC_NEUTRAL, ESC_NEUTRAL}
};

int targetR = 200;
int targetG = 50;
int targetB = 255;

// Raspberry Pi Bluetooth MAC address. Change this to your Pi's address if needed.
uint8_t raspberryBtAddress[6] = {0xE4, 0x5F, 0x01, 0x7B, 0xE6, 0x3D};

TaskHandle_t TaskLEDHandle;
TaskHandle_t TaskSensorHandle;
TaskHandle_t TaskBTHandle;
TaskHandle_t TaskMotorHandle;

void IRAM_ATTR dmpDataReady() {
    mpuInterrupt = true;
}

static void recoverI2CBus() {
    Serial.println("[2/6] Recovering I2C...");

    pinMode(I2C_SDA_PIN, INPUT_PULLUP);
    pinMode(I2C_SCL_PIN, INPUT_PULLUP);
    delay(20);

    if (digitalRead(I2C_SDA_PIN) == LOW) {
        Serial.println("-> SDA is stuck LOW. Sending SCL pulses...");
    }

    pinMode(I2C_SCL_PIN, OUTPUT_OPEN_DRAIN);
    for (int i = 0; i < 16; i++) {
        digitalWrite(I2C_SCL_PIN, LOW);
        delayMicroseconds(10);
        digitalWrite(I2C_SCL_PIN, HIGH);
        delayMicroseconds(10);
    }

    // Generate a STOP condition, then release both I2C lines.
    pinMode(I2C_SDA_PIN, OUTPUT_OPEN_DRAIN);
    digitalWrite(I2C_SDA_PIN, LOW);
    delayMicroseconds(10);
    digitalWrite(I2C_SCL_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(I2C_SDA_PIN, HIGH);
    delayMicroseconds(10);

    pinMode(I2C_SDA_PIN, INPUT_PULLUP);
    pinMode(I2C_SCL_PIN, INPUT_PULLUP);
    delay(20);

    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
    Wire.setClock(100000);

    Serial.printf("-> I2C lines: SDA=%d SCL=%d\n", digitalRead(I2C_SDA_PIN), digitalRead(I2C_SCL_PIN));
}

static bool i2cDevicePresent(uint8_t addr) {
    Wire.beginTransmission(addr);
    return Wire.endTransmission() == 0;
}

static bool initMPU6050() {
    Serial.println("[3/6] Starting MPU6050...");

    if (!i2cDevicePresent(MPU_ADDR)) {
        Serial.println("-> MPU6050 not found at 0x68. Check VCC/GND/SDA/SCL/AD0.");
        return false;
    }

    accelgyro.initialize();
    delay(50);

    if (!accelgyro.testConnection()) {
        Serial.println("-> MPU6050 testConnection() failed.");
        return false;
    }

#if RUN_BOOT_CALIBRATION
    Serial.println("-> MPU6050 connected. Calibrating, keep the cube still...");
    accelgyro.CalibrateAccel(6);
    yield();
    accelgyro.CalibrateGyro(6);
    yield();
#else
    Serial.println("-> MPU6050 connected. Boot calibration skipped.");
#endif

    accelgyro.setIntDataReadyEnabled(true);

    pinMode(MPU_INT_PIN, INPUT);
    attachInterrupt(digitalPinToInterrupt(MPU_INT_PIN), dmpDataReady, RISING);

    Serial.println("[3/6] MPU6050 ready.");
    return true;
}

static int clampEscAngle(int angle) {
    return constrain(angle, ESC_MIN_ANGLE, ESC_MAX_ANGLE);
}

static bool axisFromChar(char c, int *axis) {
    c = toupper(c);
    if (c == 'X') {
        *axis = AXIS_X;
        return true;
    }
    if (c == 'Y') {
        *axis = AXIS_Y;
        return true;
    }
    if (c == 'Z') {
        *axis = AXIS_Z;
        return true;
    }
    return false;
}

static void writeEscSafe(int axis, int angle) {
    if (axis < 0 || axis >= AXIS_COUNT) {
        return;
    }
    motorESC[axis].write(clampEscAngle(angle));
}

static void writeAllEscSafe(int angle) {
    for (int axis = 0; axis < AXIS_COUNT; axis++) {
        writeEscSafe(axis, angle);
    }
}

static void writeEscImmediate(int axis, int angle) {
    if (axis < 0 || axis >= AXIS_COUNT) {
        return;
    }
    motorESC[axis].write(clampEscAngle(angle));
}

static void writeAllEscImmediate(int angle) {
    for (int axis = 0; axis < AXIS_COUNT; axis++) {
        writeEscImmediate(axis, angle);
    }
}

static int pwmToEscAngle(float pwm, float outputLimitDeg, float minOutputDeg) {
    pwm = constrain(pwm, -255.0f, 255.0f);
    outputLimitDeg = constrain(outputLimitDeg, 0.0f, 90.0f);
    minOutputDeg = constrain(minOutputDeg, 0.0f, outputLimitDeg);

    float scaled = (pwm / 255.0f) * outputLimitDeg;
    if (fabsf(scaled) > 0.1f && fabsf(scaled) < minOutputDeg) {
        scaled = (scaled > 0.0f) ? minOutputDeg : -minOutputDeg;
    }
    return clampEscAngle(ESC_NEUTRAL + (int)round(scaled));
}

static void xyToThreeWay(float pwmX, float pwmY, int escAngle[AXIS_COUNT], float outputLimitDeg, float minOutputDeg) {
    float motorPwm[AXIS_COUNT];

    motorPwm[AXIS_X] = pwmY;
    motorPwm[AXIS_Y] = (-0.5f * pwmY) - (0.8660254f * pwmX);
    motorPwm[AXIS_Z] = (-0.5f * pwmY) + (0.8660254f * pwmX);

    for (int axis = 0; axis < AXIS_COUNT; axis++) {
        motorPwm[axis] = constrain(motorPwm[axis] * motorDirection[axis], -255.0f, 255.0f);
        escAngle[axis] = pwmToEscAngle(motorPwm[axis], outputLimitDeg, minOutputDeg);
    }
}

static void setLedColor(int r, int g, int b) {
    if (xSemaphoreTake(ledMutex, pdMS_TO_TICKS(20))) {
        targetR = constrain(r, 0, 255);
        targetG = constrain(g, 0, 255);
        targetB = constrain(b, 0, 255);
        xSemaphoreGive(ledMutex);
    }
}

static void setManualMotorAngle(int axis, int angle) {
    if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
        motorPid.autoMode = false;
        motorPid.fault = false;
        motorPid.motorEnabled[axis] = true;
        motorPid.manualEscAngle[axis] = clampEscAngle(angle);
        xSemaphoreGive(pidMutex);
    }
}

static void setOneManualMotorAngle(int axis, int angle) {
    if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
        motorPid.autoMode = false;
        motorPid.fault = false;
        for (int i = 0; i < AXIS_COUNT; i++) {
            motorPid.motorEnabled[i] = (i == axis);
            motorPid.manualEscAngle[i] = ESC_NEUTRAL;
        }
        motorPid.manualEscAngle[axis] = clampEscAngle(angle);
        xSemaphoreGive(pidMutex);
    }
}

static void setAllManualMotorAngles(int angle) {
    if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
        motorPid.fault = false;
        motorPid.autoMode = false;
        for (int axis = 0; axis < AXIS_COUNT; axis++) {
            motorPid.motorEnabled[axis] = true;
            motorPid.manualEscAngle[axis] = clampEscAngle(angle);
        }
        xSemaphoreGive(pidMutex);
    }
}

static void setOnlyMotorEnabled(int axis) {
    if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
        for (int i = 0; i < AXIS_COUNT; i++) {
            motorPid.motorEnabled[i] = (i == axis);
            if (i != axis) {
                motorPid.manualEscAngle[i] = ESC_NEUTRAL;
                motorPid.escAngle[i] = ESC_NEUTRAL;
            }
        }
        motorPid.motorSpeedX = 0.0f;
        motorPid.motorSpeedY = 0.0f;
        motorPid.fault = false;
        xSemaphoreGive(pidMutex);
    }
}

static void setAllMotorsEnabled(bool enabled) {
    if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
        for (int i = 0; i < AXIS_COUNT; i++) {
            motorPid.motorEnabled[i] = enabled;
            if (!enabled) {
                motorPid.manualEscAngle[i] = ESC_NEUTRAL;
                motorPid.escAngle[i] = ESC_NEUTRAL;
            }
        }
        motorPid.motorSpeedX = 0.0f;
        motorPid.motorSpeedY = 0.0f;
        motorPid.fault = false;
        xSemaphoreGive(pidMutex);
    }
}

static void setPidTargets(float x, float y, float z) {
    if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
        motorPid.setpointDeg[AXIS_X] = x;
        motorPid.setpointDeg[AXIS_Y] = y;
        motorPid.setpointDeg[AXIS_Z] = z;
        for (int axis = 0; axis < AXIS_COUNT; axis++) {
            motorPid.pidOutput[axis] = 0.0f;
        }
        motorPid.motorSpeedX = 0.0f;
        motorPid.motorSpeedY = 0.0f;
        motorPid.autoMode = true;
        motorPid.fault = false;
        xSemaphoreGive(pidMutex);
    }
}

static void setPidTunings(float k1, float k2, float k3) {
    if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
        motorPid.k1 = k1;
        motorPid.k2 = k2;
        motorPid.k3 = k3;
        for (int axis = 0; axis < AXIS_COUNT; axis++) {
            motorPid.pidOutput[axis] = 0.0f;
        }
        motorPid.motorSpeedX = 0.0f;
        motorPid.motorSpeedY = 0.0f;
        motorPid.fault = false;
        xSemaphoreGive(pidMutex);
    }
}

static void setPidOutputRange(float outputLimitDeg, float minOutputDeg) {
    if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
        motorPid.outputLimitDeg = constrain(outputLimitDeg, 0.0f, 90.0f);
        motorPid.minOutputDeg = constrain(minOutputDeg, 0.0f, motorPid.outputLimitDeg);
        motorPid.motorSpeedX = 0.0f;
        motorPid.motorSpeedY = 0.0f;
        motorPid.fault = false;
        xSemaphoreGive(pidMutex);
    }
}

static void printHelp() {
    Serial.println();
    Serial.println("Commands:");
    Serial.println("   LED R G B       -> set NeoPixel color, example: LED 255 0 100");
    Serial.println("    M angle        -> set all motors manually, 0~180, 90 is neutral");
    Serial.println("  M X|Y|Z angle    -> set one motor manually");
    Serial.println("  ONE X|Y|Z angle  -> set only one motor, others neutral");
    Serial.println("  ENABLE X|Y|Z     -> allow only one motor in AUTO output");
    Serial.println("  ENABLE ALL       -> allow all motors in AUTO output");
    Serial.println("  DISABLE ALL      -> force all motors neutral");
    Serial.println("  TARGET X Y Z     -> enable PID mode and set XYZ targets");
    Serial.println("  PID K1 K2 K3     -> set cube gains: angle, gyro, wheel-speed");
    Serial.println("  OUT limit min     -> set auto ESC output degrees from neutral");
    Serial.println("  DIR X|Y|Z 1|-1   -> reverse one motor direction");
    Serial.println("    AUTO 0|1       -> disable/enable PID mode");
    Serial.println("      ZERO         -> set current XYZ angles as 0 deg");
    Serial.println("    BTSTATUS       -> print Bluetooth target and connection state");
    Serial.println("     STATUS        -> print motor PID state");
    Serial.println();
}

static void printBluetoothStatus() {
    bluetoothConnected = bluetoothReady && SerialBT.connected();
    Serial.printf(
        "-> [BT] ready=%s connected=%s local=%s target=%02X:%02X:%02X:%02X:%02X:%02X\n",
        bluetoothReady ? "YES" : "NO",
        bluetoothConnected ? "YES" : "NO",
        btDeviceName,
        raspberryBtAddress[0],
        raspberryBtAddress[1],
        raspberryBtAddress[2],
        raspberryBtAddress[3],
        raspberryBtAddress[4],
        raspberryBtAddress[5]
    );
    Serial.printf("-> [BT] RFCOMM channel=%d\n", BT_RFCOMM_CHANNEL);
}

static void tryBluetoothConnect() {
    if (!bluetoothReady || SerialBT.connected()) {
        bluetoothConnected = bluetoothReady && SerialBT.connected();
        return;
    }

    Serial.println("-> [BT] connecting to Raspberry Pi...");
    bluetoothConnected = SerialBT.connect(raspberryBtAddress, BT_RFCOMM_CHANNEL);
    digitalWrite(CHECK_LED, bluetoothConnected ? LOW : HIGH);
    Serial.printf("-> [BT] Raspberry Pi connection: %s\n", bluetoothConnected ? "OK" : "FAILED");
}

static void handleCommand(String line) {
    line.trim();
    line.toUpperCase();

    if (line.length() == 0) {
        return;
    }

    int r, g, b, angle, autoValue, directionValue;
    char axisChar;
    int axis = -1;
    float targetX, targetY, targetZ, k1, k2, k3, outputLimitDeg, minOutputDeg;

    if (sscanf(line.c_str(), "LED %d %d %d", &r, &g, &b) == 3 ||
        sscanf(line.c_str(), "%d %d %d", &r, &g, &b) == 3) {
        setLedColor(r, g, b);
        Serial.printf("-> [LED] R=%d G=%d B=%d\n", constrain(r, 0, 255), constrain(g, 0, 255), constrain(b, 0, 255));
        return;
    }

    if (sscanf(line.c_str(), "M %c %d", &axisChar, &angle) == 2 && axisFromChar(axisChar, &axis)) {
        setManualMotorAngle(axis, angle);
        Serial.printf("-> [MOTOR %c] manual ESC angle: %d\n", axisNames[axis], clampEscAngle(angle));
        return;
    }

    if (sscanf(line.c_str(), "ONE %c %d", &axisChar, &angle) == 2 && axisFromChar(axisChar, &axis)) {
        setOneManualMotorAngle(axis, angle);
        Serial.printf("-> [MOTOR ONLY %c] manual ESC angle: %d, others neutral\n", axisNames[axis], clampEscAngle(angle));
        return;
    }

    if (sscanf(line.c_str(), "M %d", &angle) == 1 ||
        sscanf(line.c_str(), "MOTOR %d", &angle) == 1) {
        setAllManualMotorAngles(angle);
        Serial.printf("-> [MOTOR ALL] manual ESC angle: %d\n", clampEscAngle(angle));
        return;
    }

    if (sscanf(line.c_str(), "TARGET %f %f %f", &targetX, &targetY, &targetZ) == 3) {
        setPidTargets(targetX, targetY, targetZ);
        Serial.printf("-> [PID] target XYZ: %.2f %.2f %.2f deg\n", targetX, targetY, targetZ);
        return;
    }

    if (sscanf(line.c_str(), "PID %f %f %f", &k1, &k2, &k3) == 3) {
        setPidTunings(k1, k2, k3);
        Serial.printf("-> [PID] K1=%.3f K2=%.3f K3=%.3f\n", k1, k2, k3);
        return;
    }

    if (sscanf(line.c_str(), "OUT %f %f", &outputLimitDeg, &minOutputDeg) == 2) {
        setPidOutputRange(outputLimitDeg, minOutputDeg);
        Serial.printf("-> [PID] output limit=%.1f min=%.1f deg\n", constrain(outputLimitDeg, 0.0f, 90.0f), constrain(minOutputDeg, 0.0f, constrain(outputLimitDeg, 0.0f, 90.0f)));
        return;
    }

    if (sscanf(line.c_str(), "DIR %c %d", &axisChar, &directionValue) == 2 && axisFromChar(axisChar, &axis)) {
        motorDirection[axis] = (directionValue < 0) ? -1 : 1;
        Serial.printf("-> [DIR %c] %d\n", axisNames[axis], motorDirection[axis]);
        return;
    }

    if (sscanf(line.c_str(), "ENABLE %c", &axisChar) == 1 && axisFromChar(axisChar, &axis)) {
        setOnlyMotorEnabled(axis);
        Serial.printf("-> [ENABLE] only motor %c enabled\n", axisNames[axis]);
        return;
    }

    if (line == "ENABLE ALL") {
        setAllMotorsEnabled(true);
        Serial.println("-> [ENABLE] all motors enabled");
        return;
    }

    if (line == "DISABLE ALL" || line == "ENABLE NONE") {
        setAllMotorsEnabled(false);
        Serial.println("-> [ENABLE] all motors disabled, ESC neutral");
        return;
    }

    if (sscanf(line.c_str(), "AUTO %d", &autoValue) == 1) {
        if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
            motorPid.autoMode = (autoValue != 0);
            for (int i = 0; i < AXIS_COUNT; i++) {
                motorPid.pidOutput[i] = 0.0f;
            }
            motorPid.motorSpeedX = 0.0f;
            motorPid.motorSpeedY = 0.0f;
            motorPid.fault = false;
            xSemaphoreGive(pidMutex);
        }
        Serial.printf("-> [PID] auto mode: %s\n", autoValue ? "ON" : "OFF");
        return;
    }

    if (line == "ZERO") {
        if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
            for (int i = 0; i < AXIS_COUNT; i++) {
                motorPid.angleOffsetDeg[i] += motorPid.currentDeg[i];
                motorPid.currentDeg[i] = 0.0f;
                motorPid.pidOutput[i] = 0.0f;
            }
            motorPid.motorSpeedX = 0.0f;
            motorPid.motorSpeedY = 0.0f;
            motorPid.fault = false;
            xSemaphoreGive(pidMutex);
        }
        Serial.println("-> [PID] current XYZ angles zeroed.");
        return;
    }

    if (line == "STATUS") {
        if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(20))) {
            Serial.printf(
                "-> [STATUS] mpu=%s mode=%s fault=%s K1=%.3f K2=%.3f K3=%.3f outLimit=%.1f minOut=%.1f speedX=%.2f speedY=%.2f\n",
                mpuReady ? "READY" : "NOT_READY",
                motorPid.autoMode ? "AUTO" : "MANUAL",
                motorPid.fault ? "YES" : "NO",
                motorPid.k1,
                motorPid.k2,
                motorPid.k3,
                motorPid.outputLimitDeg,
                motorPid.minOutputDeg,
                motorPid.motorSpeedX,
                motorPid.motorSpeedY
            );
            for (int i = 0; i < AXIS_COUNT; i++) {
                Serial.printf(
                    "   %c en=%d target=%.2f current=%.2f offset=%.2f gyro=%.2f out=%.2f dir=%d esc=%d\n",
                    axisNames[i],
                    motorPid.motorEnabled[i] ? 1 : 0,
                    motorPid.setpointDeg[i],
                    motorPid.currentDeg[i],
                    motorPid.angleOffsetDeg[i],
                    motorPid.gyroRateDps[i],
                    motorPid.pidOutput[i],
                    motorDirection[i],
                    motorPid.escAngle[i]
                );
            }
            xSemaphoreGive(pidMutex);
        }
        return;
    }

    if (line == "HELP" || line == "?") {
        printHelp();
        return;
    }

    if (line == "BTSTATUS") {
        printBluetoothStatus();
        return;
    }

    Serial.println("-> Unknown command. Type HELP.");
}

void TaskLED(void *pvParameters) {
    for (;;) {
        float timeSec = millis() / 1000.0f;
        int r = 0;
        int g = 0;
        int b = 0;

        if (xSemaphoreTake(ledMutex, portMAX_DELAY)) {
            r = targetR;
            g = targetG;
            b = targetB;
            xSemaphoreGive(ledMutex);
        }

        for (int i = 0; i < NUMPIXELS; i++) {
            float pulse = (sin(timeSec * 1.5f + i * 0.4f) + 1.0f) / 2.0f;
            float intensity = 0.3f + (pulse * 0.6f);
            strip.setPixelColor(i, strip.Color(
                (uint8_t)(r * intensity),
                (uint8_t)(g * intensity),
                (uint8_t)(b * intensity)
            ));
        }
        strip.show();
        vTaskDelay(pdMS_TO_TICKS(30));
    }
}

void TaskSensor(void *pvParameters) {
    TickType_t lastWake = xTaskGetTickCount();
    uint32_t lastMicros = micros();
    bool filterInitialized = false;

    for (;;) {
        if (!mpuReady) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        SensorData sample;
        accelgyro.getMotion6(&sample.ax, &sample.ay, &sample.az, &sample.gx, &sample.gy, &sample.gz);

        uint32_t nowMicros = micros();
        float dt = (nowMicros - lastMicros) / 1000000.0f;
        lastMicros = nowMicros;
        if (dt <= 0.0f || dt > 0.2f) {
            dt = 0.01f;
        }

        if (xSemaphoreTake(sensorMutex, pdMS_TO_TICKS(5))) {
            currentData = sample;
            xSemaphoreGive(sensorMutex);
        }

        float accelAngleX = atan2f((float)sample.ay, (float)sample.az) * RAD_TO_DEG;
        float accelAngleY = atan2f(-(float)sample.ax, sqrtf((float)sample.ay * sample.ay + (float)sample.az * sample.az)) * RAD_TO_DEG;
        float gyroRate[AXIS_COUNT] = {
            sample.gx / 131.0f,
            sample.gy / 131.0f,
            sample.gz / 131.0f
        };

        if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(5))) {
            if (!filterInitialized) {
                motorPid.currentDeg[AXIS_X] = accelAngleX - motorPid.angleOffsetDeg[AXIS_X];
                motorPid.currentDeg[AXIS_Y] = accelAngleY - motorPid.angleOffsetDeg[AXIS_Y];
                motorPid.currentDeg[AXIS_Z] = 0.0f;
                filterInitialized = true;
            } else {
                float rawX = motorPid.currentDeg[AXIS_X] + motorPid.angleOffsetDeg[AXIS_X];
                float rawY = motorPid.currentDeg[AXIS_Y] + motorPid.angleOffsetDeg[AXIS_Y];
                float rawZ = motorPid.currentDeg[AXIS_Z] + motorPid.angleOffsetDeg[AXIS_Z];

                rawX = (COMPLEMENTARY_ALPHA * (rawX + gyroRate[AXIS_X] * dt)) +
                       ((1.0f - COMPLEMENTARY_ALPHA) * accelAngleX);
                rawY = (COMPLEMENTARY_ALPHA * (rawY + gyroRate[AXIS_Y] * dt)) +
                       ((1.0f - COMPLEMENTARY_ALPHA) * accelAngleY);
                rawZ += gyroRate[AXIS_Z] * dt;

                motorPid.currentDeg[AXIS_X] = rawX - motorPid.angleOffsetDeg[AXIS_X];
                motorPid.currentDeg[AXIS_Y] = rawY - motorPid.angleOffsetDeg[AXIS_Y];
                motorPid.currentDeg[AXIS_Z] = rawZ - motorPid.angleOffsetDeg[AXIS_Z];
            }

            for (int axis = 0; axis < AXIS_COUNT; axis++) {
                motorPid.gyroRateDps[axis] = gyroRate[axis];
            }
            xSemaphoreGive(pidMutex);
        }

        vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(10));
    }
}

void TaskMotor(void *pvParameters) {
    writeAllEscImmediate(ESC_NEUTRAL);
    Serial.println("-> [MOTOR] ESC arming all motors at neutral for 5 seconds...");
    vTaskDelay(pdMS_TO_TICKS(5000));

    const float alpha = 0.7f;

    for (;;) {
        int escAngle[AXIS_COUNT] = {ESC_NEUTRAL, ESC_NEUTRAL, ESC_NEUTRAL};

        if (xSemaphoreTake(pidMutex, pdMS_TO_TICKS(10))) {
            if (motorPid.autoMode) {
                if (fabsf(motorPid.currentDeg[AXIS_X]) > BALANCE_FALL_ANGLE ||
                    fabsf(motorPid.currentDeg[AXIS_Y]) > BALANCE_FALL_ANGLE) {
                    motorPid.fault = true;
                    motorPid.autoMode = false;
                    for (int axis = 0; axis < AXIS_COUNT; axis++) {
                        motorPid.pidOutput[axis] = 0.0f;
                        escAngle[axis] = ESC_NEUTRAL;
                    }
                    motorPid.motorSpeedX = 0.0f;
                    motorPid.motorSpeedY = 0.0f;
                } else {
                    float angleX = motorPid.currentDeg[AXIS_X] - motorPid.setpointDeg[AXIS_X];
                    float angleY = motorPid.currentDeg[AXIS_Y] - motorPid.setpointDeg[AXIS_Y];

                    motorPid.gyroYfilt = (alpha * motorPid.gyroRateDps[AXIS_Y]) + ((1.0f - alpha) * motorPid.gyroYfilt);
                    motorPid.gyroZfilt = (alpha * motorPid.gyroRateDps[AXIS_Z]) + ((1.0f - alpha) * motorPid.gyroZfilt);

                    float pwmX = (motorPid.k1 * angleX) +
                                 (motorPid.k2 * motorPid.gyroZfilt) +
                                 (motorPid.k3 * motorPid.motorSpeedX);
                    float pwmY = (motorPid.k1 * angleY) +
                                 (motorPid.k2 * motorPid.gyroYfilt) +
                                 (motorPid.k3 * motorPid.motorSpeedY);

                    pwmX = constrain(pwmX, -255.0f, 255.0f);
                    pwmY = constrain(pwmY, -255.0f, 255.0f);

                    if (fabsf(motorPid.k3) > 0.0001f) {
                        motorPid.motorSpeedX += pwmX;
                        motorPid.motorSpeedY += pwmY;
                        motorPid.motorSpeedX = constrain(motorPid.motorSpeedX, -800.0f, 800.0f);
                        motorPid.motorSpeedY = constrain(motorPid.motorSpeedY, -800.0f, 800.0f);
                    } else {
                        motorPid.motorSpeedX = 0.0f;
                        motorPid.motorSpeedY = 0.0f;
                    }

                    xyToThreeWay(pwmX, pwmY, escAngle, motorPid.outputLimitDeg, motorPid.minOutputDeg);

                    motorPid.pidOutput[AXIS_X] = pwmX;
                    motorPid.pidOutput[AXIS_Y] = pwmY;
                    motorPid.pidOutput[AXIS_Z] = 0.0f;
                }
            } else {
                for (int axis = 0; axis < AXIS_COUNT; axis++) {
                    escAngle[axis] = motorPid.manualEscAngle[axis];
                }
            }

            for (int axis = 0; axis < AXIS_COUNT; axis++) {
                if (!motorPid.motorEnabled[axis]) {
                    escAngle[axis] = ESC_NEUTRAL;
                }
                motorPid.escAngle[axis] = escAngle[axis];
            }
            xSemaphoreGive(pidMutex);
        }

        for (int axis = 0; axis < AXIS_COUNT; axis++) {
            writeEscSafe(axis, escAngle[axis]);
        }
        vTaskDelay(pdMS_TO_TICKS(PID_LOOP_MS));
    }
}

void TaskBT(void *pvParameters) {
    uint32_t lastBtRetry = 0;

    for (;;) {
        if (Serial.available() > 0) {
            String line = Serial.readStringUntil('\n');
            handleCommand(line);
        }

        if (bluetoothReady && !SerialBT.connected() && millis() - lastBtRetry >= BT_RETRY_MS) {
            lastBtRetry = millis();
            tryBluetoothConnect();
        }

        if (bluetoothReady && SerialBT.connected() && SerialBT.available() > 0) {
            String line = SerialBT.readStringUntil('\n');
            handleCommand(line);
        }

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

// void BTconnect() {
//     Serial.println("Trying Bluetooth connection...");
//
//     if (SerialBT.connect(address)) {
//         digitalWrite(CHECK_LED, LOW);
//         Serial.println("Bluetooth connected.");
//     } else {
//         digitalWrite(CHECK_LED, HIGH);
//         Serial.println("Bluetooth connection failed. Retrying later.");
//         vTaskDelay(pdMS_TO_TICKS(2000));
//     }
// }

void setup() {
    Serial.begin(115200);
    Serial.setTimeout(50);
    delay(200);
    Serial.println("\n[1/7] Serial Start");

    pinMode(CHECK_LED, OUTPUT);
    digitalWrite(CHECK_LED, HIGH);

    recoverI2CBus();
    mpuReady = initMPU6050();

    Serial.println("[4/7] Creating mutexes and starting hardware...");
    ledMutex = xSemaphoreCreateMutex();
    sensorMutex = xSemaphoreCreateMutex();
    pidMutex = xSemaphoreCreateMutex();

    ESP32PWM::allocateTimer(1);
    ESP32PWM::allocateTimer(2);
    ESP32PWM::allocateTimer(3);
    for (int axis = 0; axis < AXIS_COUNT; axis++) {
        motorESC[axis].setPeriodHertz(50);
        motorESC[axis].attach(motorPins[axis], ESC_MIN_US, ESC_MAX_US);
        writeEscImmediate(axis, ESC_NEUTRAL);
    }

    Serial.println("[5/7] Starting Bluetooth...");
    SerialBT.setTimeout(50);
    if (SerialBT.begin(btDeviceName, true)) {
        bluetoothReady = true;
        printBluetoothStatus();
        tryBluetoothConnect();
    } else {
        bluetoothReady = false;
        digitalWrite(CHECK_LED, HIGH);
        Serial.println("-> Bluetooth start failed.");
    }

    Serial.println("[6/7] Starting NeoPixel...");
    strip.begin();
    strip.setBrightness(50);
    strip.show();

    Serial.println("[7/7] Creating FreeRTOS tasks...");
    xTaskCreatePinnedToCore(TaskLED, "TaskLED", 4096, NULL, 1, &TaskLEDHandle, 1);
    delay(100);
    xTaskCreatePinnedToCore(TaskSensor, "TaskSensor", 4096, NULL, 2, &TaskSensorHandle, 1);
    delay(100);
    xTaskCreatePinnedToCore(TaskBT, "TaskBT", 8192, NULL, 1, &TaskBTHandle, 1);
    delay(100);
    xTaskCreatePinnedToCore(TaskMotor, "TaskMotor", 4096, NULL, 2, &TaskMotorHandle, 0);
    delay(100);

    Serial.println("--- Setup Complete ---");
    printHelp();
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(1000));
}
