#include <Adafruit_NeoPixel.h>
#include <BluetoothSerial.h>
#include <ESP32Servo.h>
#include <I2Cdev.h>
#include <MPU6050.h>
#include <Wire.h>
#include <ctype.h>
#include <math.h>

#ifndef OUTPUT_OPEN_DRAIN
#define OUTPUT_OPEN_DRAIN OUTPUT
#endif

#ifndef RAD_TO_DEG
#define RAD_TO_DEG 57.2957795131f
#endif

namespace Config {
constexpr int CHECK_LED_PIN = 5;
constexpr int LED_PIN = 13;
constexpr int LED_COUNT = 144;
constexpr int MOTOR_Z_PIN = 12;
constexpr int I2C_SDA_PIN = 21;
constexpr int I2C_SCL_PIN = 22;
constexpr uint8_t MPU_ADDRESS = 0x68;

constexpr int ESC_MIN_US = 1000;
constexpr int ESC_MAX_US = 2000;
constexpr int ESC_NEUTRAL = 90;
constexpr int ESC_MIN_ANGLE = 0;
constexpr int ESC_MAX_ANGLE = 180;
constexpr int ESC_AUTO_RAMP_STEP = 4;
constexpr int ESC_MANUAL_RAMP_STEP = 3;
constexpr uint32_t ESC_ARM_TIME_MS = 5000;

constexpr uint32_t SENSOR_LOOP_MS = 10;
constexpr uint32_t CONTROL_LOOP_MS = 20;
constexpr float CONTROL_DT_FALLBACK_SEC = CONTROL_LOOP_MS / 1000.0f;
constexpr float COMPLEMENTARY_FILTER_TAU_SEC = 0.49f;
constexpr float GYRO_FILTER_TAU_SEC = 0.01f;
constexpr uint32_t SENSOR_STALE_TIMEOUT_US = 100000;
constexpr float ACCEL_TRUST_MIN_G = 0.80f;
constexpr float ACCEL_TRUST_MAX_G = 1.20f;
constexpr float ACCEL_ANGLE_INNOVATION_LIMIT_DEG = 6.0f;
constexpr float GYRO_SPIKE_DIFFERENCE_DPS = 25.0f;

constexpr float DEFAULT_KP = 35.0f;
constexpr float DEFAULT_KI = 15.0f;
constexpr float DEFAULT_KD = 40.0f;
constexpr float DEFAULT_OUTPUT_LIMIT_DEG = 40.0f;
constexpr float DEFAULT_MIN_OUTPUT_DEG = 5.0f;
constexpr int DEFAULT_MOTOR_DIRECTION = -1;

constexpr float COMMAND_LIMIT = 255.0f;
constexpr float ANGLE_DEADBAND_DEG = 0.35f;
constexpr float GYRO_DEADBAND_DPS = 1.5f;
constexpr float INTEGRAL_OUTPUT_LIMIT = 60.0f;
constexpr float INTEGRAL_ACTIVE_ANGLE_DEG = 5.0f;
constexpr float BALANCE_ACTIVE_ANGLE_DEG = 20.0f;
constexpr float TARGET_LIMIT_DEG = 15.0f;

constexpr bool RUN_BOOT_CALIBRATION = true;
constexpr int BT_RFCOMM_CHANNEL = 1;
constexpr const char *BT_DEVICE_NAME = "ESP32-Cube-blue";
}  // namespace Config

struct BalanceState {
    float kp = Config::DEFAULT_KP;
    float ki = Config::DEFAULT_KI;
    float kd = Config::DEFAULT_KD;

    float targetAngleDeg = 0.0f;
    float angleDeg = 0.0f;
    float angleOffsetDeg = 0.0f;
    float gyroRateDps = 0.0f;
    float filteredGyroRateDps = 0.0f;
    float accelNormG = 1.0f;
    float proportionalTerm = 0.0f;
    float integralTerm = 0.0f;
    float derivativeTerm = 0.0f;
    float outputCommand = 0.0f;
    float saturationTimeSec = 0.0f;

    float outputLimitDeg = Config::DEFAULT_OUTPUT_LIMIT_DEG;
    float minOutputDeg = Config::DEFAULT_MIN_OUTPUT_DEG;

    int motorDirection = Config::DEFAULT_MOTOR_DIRECTION;
    int manualEscAngle = Config::ESC_NEUTRAL;
    int escAngle = Config::ESC_NEUTRAL;
    uint32_t sensorUpdateMicros = 0;
    uint32_t gyroSpikeCount = 0;

    bool balanceEnabled = false;
    bool motorEnabled = true;
    bool fault = false;
    bool forceNeutral = true;
    bool outputSaturated = false;
    bool accelTrusted = true;
};

Adafruit_NeoPixel strip(
    Config::LED_COUNT,
    Config::LED_PIN,
    NEO_GRB + NEO_KHZ800
);
BluetoothSerial SerialBT;
MPU6050 mpu;
Servo motorEsc;

SemaphoreHandle_t ledMutex = nullptr;
SemaphoreHandle_t balanceMutex = nullptr;

BalanceState balance;
bool mpuReady = false;
bool bluetoothReady = false;
bool bluetoothConnected = false;

int targetR = 200;
int targetG = 50;
int targetB = 255;

static int clampEscAngle(int angle) {
    return constrain(angle, Config::ESC_MIN_ANGLE, Config::ESC_MAX_ANGLE);
}

static float medianOfThree(float a, float b, float c) {
    return max(min(a, b), min(max(a, b), c));
}

static float elapsedSeconds(uint32_t *lastMicros, float fallbackSec) {
    uint32_t nowMicros = micros();
    float dtSec = (nowMicros - *lastMicros) / 1000000.0f;
    *lastMicros = nowMicros;

    if (dtSec <= 0.0f || dtSec > 0.2f) {
        return fallbackSec;
    }
    return dtSec;
}

static void resetControllerLocked() {
    balance.filteredGyroRateDps = 0.0f;
    balance.proportionalTerm = 0.0f;
    balance.integralTerm = 0.0f;
    balance.derivativeTerm = 0.0f;
    balance.outputCommand = 0.0f;
    balance.saturationTimeSec = 0.0f;
    balance.outputSaturated = false;
}

static void requestNeutralLocked() {
    balance.balanceEnabled = false;
    balance.manualEscAngle = Config::ESC_NEUTRAL;
    balance.forceNeutral = true;
    resetControllerLocked();
}

static int rampEscAngle(int current, int target, int maxStep) {
    current = clampEscAngle(current);
    target = clampEscAngle(target);
    maxStep = max(1, maxStep);

    int delta = target - current;
    if (abs(delta) <= maxStep) {
        return target;
    }
    return current + ((delta > 0) ? maxStep : -maxStep);
}

static int commandToEscAngle(
    float command,
    float outputLimitDeg,
    float minOutputDeg
) {
    command = constrain(command, -Config::COMMAND_LIMIT, Config::COMMAND_LIMIT);
    if (fabsf(command) < 0.5f) {
        return Config::ESC_NEUTRAL;
    }

    outputLimitDeg = constrain(outputLimitDeg, 0.0f, 90.0f);
    minOutputDeg = constrain(minOutputDeg, 0.0f, outputLimitDeg);
    float offsetDeg =
        (command / Config::COMMAND_LIMIT) * outputLimitDeg;
    if (fabsf(offsetDeg) < minOutputDeg) {
        offsetDeg = (offsetDeg > 0.0f)
            ? minOutputDeg
            : -minOutputDeg;
    }

    return clampEscAngle(
        Config::ESC_NEUTRAL + static_cast<int>(roundf(offsetDeg))
    );
}

// Uses proportional-on-error, derivative-on-measurement, and a clamped
// integrator, matching the control structure used by Arduino PID_v1.
static float computeBalancePidLocked(
    float errorDeg,
    float gyroRateDps,
    float dtSec
) {
    balance.proportionalTerm = balance.kp * errorDeg;
    balance.derivativeTerm = -balance.kd * gyroRateDps;

    bool integralActive =
        fabsf(errorDeg) <= Config::INTEGRAL_ACTIVE_ANGLE_DEG &&
        balance.ki > 0.0f;
    if (integralActive) {
        float nextIntegralTerm = constrain(
            balance.integralTerm + (balance.ki * errorDeg * dtSec),
            -Config::INTEGRAL_OUTPUT_LIMIT,
            Config::INTEGRAL_OUTPUT_LIMIT
        );
        float candidate =
            balance.proportionalTerm +
            nextIntegralTerm +
            balance.derivativeTerm;
        bool pushesFurtherIntoSaturation =
            (candidate > Config::COMMAND_LIMIT && errorDeg > 0.0f) ||
            (candidate < -Config::COMMAND_LIMIT && errorDeg < 0.0f);
        if (!pushesFurtherIntoSaturation) {
            balance.integralTerm = nextIntegralTerm;
        }
    } else {
        balance.integralTerm = 0.0f;
    }

    float output =
        balance.proportionalTerm +
        balance.integralTerm +
        balance.derivativeTerm;
    balance.outputCommand = constrain(
        output,
        -Config::COMMAND_LIMIT,
        Config::COMMAND_LIMIT
    );
    return balance.outputCommand;
}

static void recoverI2CBus() {
    Serial.println("[2/6] Recovering I2C bus...");

    pinMode(Config::I2C_SDA_PIN, INPUT_PULLUP);
    pinMode(Config::I2C_SCL_PIN, INPUT_PULLUP);
    delay(20);

    if (digitalRead(Config::I2C_SDA_PIN) == LOW) {
        pinMode(Config::I2C_SCL_PIN, OUTPUT_OPEN_DRAIN);
        for (int pulse = 0; pulse < 16; pulse++) {
            digitalWrite(Config::I2C_SCL_PIN, LOW);
            delayMicroseconds(10);
            digitalWrite(Config::I2C_SCL_PIN, HIGH);
            delayMicroseconds(10);
        }

        pinMode(Config::I2C_SDA_PIN, OUTPUT_OPEN_DRAIN);
        digitalWrite(Config::I2C_SDA_PIN, LOW);
        delayMicroseconds(10);
        digitalWrite(Config::I2C_SCL_PIN, HIGH);
        delayMicroseconds(10);
        digitalWrite(Config::I2C_SDA_PIN, HIGH);
        delayMicroseconds(10);
    }

    pinMode(Config::I2C_SDA_PIN, INPUT_PULLUP);
    pinMode(Config::I2C_SCL_PIN, INPUT_PULLUP);
    Wire.begin(Config::I2C_SDA_PIN, Config::I2C_SCL_PIN);
    Wire.setClock(100000);
}

static bool i2cDevicePresent(uint8_t address) {
    Wire.beginTransmission(address);
    return Wire.endTransmission() == 0;
}

static bool initializeMpu() {
    Serial.println("[3/6] Starting MPU6050...");
    if (!i2cDevicePresent(Config::MPU_ADDRESS)) {
        Serial.println("-> MPU6050 not found at 0x68. Check wiring and AD0.");
        return false;
    }

    mpu.initialize();
    delay(50);
    if (!mpu.testConnection()) {
        Serial.println("-> MPU6050 connection test failed.");
        return false;
    }

    // MPU6050 register value 3 enables its internal ~42 Hz gyro DLPF.
    mpu.setDLPFMode(3);
    mpu.setRate(9);  // 1 kHz / (1 + 9) = 100 Hz sample rate.

    if (Config::RUN_BOOT_CALIBRATION) {
        Serial.println("-> Calibrating MPU6050. Keep the cube still...");
        mpu.CalibrateAccel(6);
        yield();
        mpu.CalibrateGyro(6);
        yield();
    }

    Serial.println("-> MPU6050 ready. Balance input is the physical X axis.");
    return true;
}

static void writeMotorEsc(int angle) {
    motorEsc.write(clampEscAngle(angle));
}

static void setLedColor(int r, int g, int b) {
    if (xSemaphoreTake(ledMutex, pdMS_TO_TICKS(20))) {
        targetR = constrain(r, 0, 255);
        targetG = constrain(g, 0, 255);
        targetB = constrain(b, 0, 255);
        xSemaphoreGive(ledMutex);
    }
}

static void setManualEscAngle(int angle) {
    if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
        balance.balanceEnabled = false;
        balance.motorEnabled = true;
        balance.fault = false;
        balance.manualEscAngle = clampEscAngle(angle);
        balance.forceNeutral = false;
        resetControllerLocked();
        xSemaphoreGive(balanceMutex);
    }
}

static void stopMotor(bool disableMotor) {
    if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
        requestNeutralLocked();
        balance.motorEnabled = !disableMotor;
        xSemaphoreGive(balanceMutex);
    }
}

static bool setBalanceEnabled(bool enabled) {
    bool success = true;
    if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
        if (enabled && !mpuReady) {
            requestNeutralLocked();
            balance.fault = true;
            success = false;
        } else if (enabled) {
            balance.balanceEnabled = true;
            balance.motorEnabled = true;
            balance.manualEscAngle = Config::ESC_NEUTRAL;
            balance.forceNeutral = false;
            balance.fault = false;
            resetControllerLocked();
        } else {
            requestNeutralLocked();
        }
        xSemaphoreGive(balanceMutex);
    } else {
        success = false;
    }
    return success;
}

static float setBalanceTarget(float targetDeg, bool *started) {
    float limitedTarget = constrain(
        targetDeg,
        -Config::TARGET_LIMIT_DEG,
        Config::TARGET_LIMIT_DEG
    );
    *started = false;

    if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
        balance.targetAngleDeg = limitedTarget;
        if (mpuReady) {
            balance.balanceEnabled = true;
            balance.motorEnabled = true;
            balance.manualEscAngle = Config::ESC_NEUTRAL;
            balance.forceNeutral = false;
            balance.fault = false;
            resetControllerLocked();
            *started = true;
        } else {
            requestNeutralLocked();
            balance.fault = true;
        }
        xSemaphoreGive(balanceMutex);
    }
    return limitedTarget;
}

static void setPidTunings(float kp, float ki, float kd) {
    if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
        balance.kp = constrain(kp, 0.0f, 100.0f);
        balance.ki = constrain(ki, 0.0f, 50.0f);
        balance.kd = constrain(kd, 0.0f, 50.0f);
        resetControllerLocked();
        xSemaphoreGive(balanceMutex);
    }
}

static void setOutputRange(float outputLimitDeg, float minOutputDeg) {
    if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
        balance.outputLimitDeg = constrain(outputLimitDeg, 0.0f, 90.0f);
        balance.minOutputDeg = constrain(
            minOutputDeg,
            0.0f,
            balance.outputLimitDeg
        );
        resetControllerLocked();
        xSemaphoreGive(balanceMutex);
    }
}

static void setMotorDirection(int direction) {
    if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
        balance.motorDirection = (direction < 0) ? -1 : 1;
        requestNeutralLocked();
        xSemaphoreGive(balanceMutex);
    }
}

static void zeroBalanceAngle() {
    if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
        requestNeutralLocked();
        balance.angleOffsetDeg += balance.angleDeg;
        balance.angleDeg = 0.0f;
        balance.fault = false;
        xSemaphoreGive(balanceMutex);
    }
}

static void printHelp() {
    Serial.println();
    Serial.println("Single-axis balancing commands (MPU X -> motor Z):");
    Serial.println("  LED R G B          set NeoPixel color");
    Serial.println("  M angle            manual Z ESC angle, 90 is neutral");
    Serial.println("  M Z angle          same as M angle");
    Serial.println("  STOP               stop Z motor immediately");
    Serial.println("  ENABLE Z           enable manual Z motor control");
    Serial.println("  DISABLE Z          disable Z motor and force neutral");
    Serial.println("  TARGET deg         set target (-15..15) and start balance");
    Serial.println("  PID Kp Ki Kd       set angle PID gains");
    Serial.println("  OUT limit min      set bidirectional correction and minimum offset");
    Serial.println("  DIR Z 1|-1         set Z motor direction, then stop");
    Serial.println("  BALANCE ON|OFF     start or stop balancing");
    Serial.println("  ZERO               stop and zero the current X angle");
    Serial.println("  STATUS             print controller state");
    Serial.println("  BTSTATUS           print Bluetooth state");
    Serial.println("  APPSTATE           send one app state line over Bluetooth");
    Serial.println();
}

static void refreshBluetoothConnection() {
    bluetoothConnected = bluetoothReady && SerialBT.connected();
    digitalWrite(
        Config::CHECK_LED_PIN,
        bluetoothConnected ? LOW : HIGH
    );
}

static void printBluetoothStatus() {
    refreshBluetoothConnection();
    Serial.printf(
        "-> [BT] ready=%s connected=%s name=%s channel=%d\n",
        bluetoothReady ? "YES" : "NO",
        bluetoothConnected ? "YES" : "NO",
        Config::BT_DEVICE_NAME,
        Config::BT_RFCOMM_CHANNEL
    );
}

static BalanceState getBalanceSnapshot() {
    BalanceState snapshot;
    if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
        snapshot = balance;
        xSemaphoreGive(balanceMutex);
    }
    return snapshot;
}

static void printStatus() {
    BalanceState state = getBalanceSnapshot();
    uint32_t sensorAgeMs = state.sensorUpdateMicros == 0
        ? UINT32_MAX
        : (micros() - state.sensorUpdateMicros) / 1000;
    float correctionLimitDeg = constrain(state.outputLimitDeg, 0.0f, 90.0f);
    float autoMinPwm = Config::ESC_NEUTRAL - correctionLimitDeg;
    float autoMaxPwm = Config::ESC_NEUTRAL + correctionLimitDeg;
    Serial.printf(
        "-> [STATUS] mpu=%s mode=%s control=BIDIRECTIONAL fault=%s enabled=%d\n",
        mpuReady ? "READY" : "NOT_READY",
        state.balanceEnabled ? "BALANCE" : "MANUAL",
        state.fault ? "YES" : "NO",
        state.motorEnabled ? 1 : 0
    );
    Serial.printf(
        "   angle=%.2f target=%.2f gyro=%.2f offset=%.2f sensorAge=%lums\n",
        state.angleDeg,
        state.targetAngleDeg,
        state.gyroRateDps,
        state.angleOffsetDeg,
        static_cast<unsigned long>(sensorAgeMs)
    );
    Serial.printf(
        "   accel=%.3fg trusted=%d gyroSpikes=%lu\n",
        state.accelNormG,
        state.accelTrusted ? 1 : 0,
        static_cast<unsigned long>(state.gyroSpikeCount)
    );
    Serial.printf(
        "   Kp=%.3f Ki=%.3f Kd=%.3f P=%.2f I=%.2f D=%.2f command=%.2f\n",
        state.kp,
        state.ki,
        state.kd,
        state.proportionalTerm,
        state.integralTerm,
        state.derivativeTerm,
        state.outputCommand
    );
    Serial.printf(
        "   outRequest=%.1f correction=%.1f minOffset=%.1f\n",
        state.outputLimitDeg,
        correctionLimitDeg,
        state.minOutputDeg
    );
    Serial.printf(
        "   autoPwm=%.0f - 90 - %.0f dir=%d pwm=%d saturated=%d time=%.2fs\n",
        autoMinPwm,
        autoMaxPwm,
        state.motorDirection,
        state.escAngle,
        state.outputSaturated ? 1 : 0,
        state.saturationTimeSec
    );
}

static void sendAppStateLine() {
    if (!bluetoothReady || !SerialBT.connected()) {
        return;
    }

    BalanceState state = getBalanceSnapshot();
    int r = 0;
    int g = 0;
    int b = 0;
    if (xSemaphoreTake(ledMutex, pdMS_TO_TICKS(20))) {
        r = targetR;
        g = targetG;
        b = targetB;
        xSemaphoreGive(ledMutex);
    }

    SerialBT.printf(
        "STATE mpu=%d auto=%d fault=%d led=%d,%d,%d "
        "kp=%.3f ki=%.3f kd=%.3f kw=0.000 sensor=0.0 "
        "out=%.1f min=%.1f ex=0 ey=0 ez=%d mx=90 my=90 mz=%d "
        "x=%.2f y=0.00 z=0.00\n",
        mpuReady ? 1 : 0,
        state.balanceEnabled ? 1 : 0,
        state.fault ? 1 : 0,
        r,
        g,
        b,
        state.kp,
        state.ki,
        state.kd,
        state.outputLimitDeg,
        state.minOutputDeg,
        state.motorEnabled ? 1 : 0,
        state.escAngle,
        state.angleDeg
    );
}

static bool commandUsesZAxis(char axisChar) {
    return toupper(static_cast<unsigned char>(axisChar)) == 'Z';
}

static void handleCommand(String line) {
    line.trim();
    line.toUpperCase();
    if (line.length() == 0) {
        return;
    }

    if (line == "CONNECTED TO BLUETOOTH SERVER" ||
        line == "UNDEFINED VALUE" ||
        line == "NO VALUE" ||
        line == "LED TOGGLED") {
        return;
    }

    int r, g, b, angle, direction, enabled;
    float targetDeg, kp, ki, kd, outputLimitDeg, minOutputDeg;
    char axisChar;

    if (sscanf(line.c_str(), "LED %d %d %d", &r, &g, &b) == 3 ||
        sscanf(line.c_str(), "%d %d %d", &r, &g, &b) == 3) {
        setLedColor(r, g, b);
        Serial.printf(
            "-> [LED] R=%d G=%d B=%d\n",
            constrain(r, 0, 255),
            constrain(g, 0, 255),
            constrain(b, 0, 255)
        );
        return;
    }

    if (sscanf(line.c_str(), "M %d", &angle) == 1 ||
        sscanf(line.c_str(), "MOTOR %d", &angle) == 1) {
        setManualEscAngle(angle);
        Serial.printf("-> [MOTOR Z] manual ESC angle=%d\n", clampEscAngle(angle));
        return;
    }

    if (sscanf(line.c_str(), "M %c %d", &axisChar, &angle) == 2) {
        if (!commandUsesZAxis(axisChar)) {
            Serial.println("-> Only motor Z is available in single-axis mode.");
            return;
        }
        setManualEscAngle(angle);
        Serial.printf("-> [MOTOR Z] manual ESC angle=%d\n", clampEscAngle(angle));
        return;
    }

    if (line == "STOP" || line == "M STOP") {
        stopMotor(false);
        Serial.println("-> [MOTOR Z] stopped at neutral.");
        return;
    }

    if (sscanf(line.c_str(), "TARGET %f", &targetDeg) == 1) {
        bool started = false;
        float actualTarget = setBalanceTarget(targetDeg, &started);
        Serial.printf(
            "-> [PID] target=%.2f deg, balance=%s\n",
            actualTarget,
            started ? "ON" : "FAILED: MPU NOT READY"
        );
        return;
    }

    if (sscanf(line.c_str(), "PID %f %f %f", &kp, &ki, &kd) == 3) {
        setPidTunings(kp, ki, kd);
        BalanceState state = getBalanceSnapshot();
        Serial.printf(
            "-> [PID] Kp=%.3f Ki=%.3f Kd=%.3f\n",
            state.kp,
            state.ki,
            state.kd
        );
        return;
    }

    if (sscanf(
            line.c_str(),
            "OUT %f %f",
            &outputLimitDeg,
            &minOutputDeg
        ) == 2) {
        setOutputRange(outputLimitDeg, minOutputDeg);
        BalanceState state = getBalanceSnapshot();
        Serial.printf(
            "-> [PID] output limit=%.1f min=%.1f deg\n",
            state.outputLimitDeg,
            state.minOutputDeg
        );
        return;
    }

    if (sscanf(line.c_str(), "DIR %c %d", &axisChar, &direction) == 2) {
        if (!commandUsesZAxis(axisChar)) {
            Serial.println("-> Only motor Z direction can be changed.");
            return;
        }
        setMotorDirection(direction);
        Serial.printf(
            "-> [DIR Z] %d, motor stopped\n",
            getBalanceSnapshot().motorDirection
        );
        return;
    }

    if (line == "ENABLE Z" || line == "ENABLE") {
        if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(20))) {
            balance.motorEnabled = true;
            balance.fault = false;
            xSemaphoreGive(balanceMutex);
        }
        Serial.println("-> [MOTOR Z] enabled.");
        return;
    }

    if (line == "DISABLE Z" || line == "DISABLE ALL" ||
        line == "ENABLE NONE") {
        stopMotor(true);
        Serial.println("-> [MOTOR Z] disabled and neutral.");
        return;
    }

    if (sscanf(line.c_str(), "AUTO %d", &enabled) == 1) {
        bool success = setBalanceEnabled(enabled != 0);
        Serial.printf(
            "-> [PID] balance=%s\n",
            enabled ? (success ? "ON" : "FAILED: MPU NOT READY") : "OFF"
        );
        return;
    }

    if (line == "BALANCE ON" || line == "BALANCE 1" ||
        line == "BALANCE START") {
        bool success = setBalanceEnabled(true);
        Serial.printf(
            "-> [PID] balance=%s\n",
            success ? "ON" : "FAILED: MPU NOT READY"
        );
        return;
    }

    if (line == "BALANCE OFF" || line == "BALANCE 0" ||
        line == "BALANCE STOP") {
        setBalanceEnabled(false);
        Serial.println("-> [PID] balance=OFF, ESC neutral.");
        return;
    }

    if (line == "ZERO") {
        zeroBalanceAngle();
        Serial.println("-> [SENSOR X] angle zeroed, balance stopped.");
        return;
    }

    if (line == "STATUS") {
        printStatus();
        return;
    }

    if (line == "BTSTATUS") {
        printBluetoothStatus();
        return;
    }

    if (line == "APPSTATE") {
        sendAppStateLine();
        return;
    }

    if (line == "HELP" || line == "?") {
        printHelp();
        return;
    }

    Serial.println("-> Unknown command. Type HELP.");
}

void TaskLed(void *parameter) {
    TickType_t lastWake = xTaskGetTickCount();

    for (;;) {
        int r = 0;
        int g = 0;
        int b = 0;
        if (xSemaphoreTake(ledMutex, portMAX_DELAY)) {
            r = targetR;
            g = targetG;
            b = targetB;
            xSemaphoreGive(ledMutex);
        }

        float timeSec = millis() / 1000.0f;
        for (int pixel = 0; pixel < Config::LED_COUNT; pixel++) {
            float pulse =
                (sinf(timeSec * 1.5f + pixel * 0.4f) + 1.0f) * 0.5f;
            float intensity = 0.3f + pulse * 0.6f;
            strip.setPixelColor(
                pixel,
                strip.Color(
                    static_cast<uint8_t>(r * intensity),
                    static_cast<uint8_t>(g * intensity),
                    static_cast<uint8_t>(b * intensity)
                )
            );
        }
        strip.show();
        vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(30));
    }
}

void TaskSensor(void *parameter) {
    TickType_t lastWake = xTaskGetTickCount();
    uint32_t lastMicros = micros();
    float filteredAngleDeg = 0.0f;
    bool filterInitialized = false;
    float previousGyroRateDps = 0.0f;
    float olderGyroRateDps = 0.0f;
    uint8_t gyroHistoryCount = 0;

    for (;;) {
        if (!mpuReady) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        int16_t ax, ay, az, gx, gy, gz;
        mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
        float dtSec = elapsedSeconds(
            &lastMicros,
            Config::SENSOR_LOOP_MS / 1000.0f
        );

        float accelAngleXDeg =
            atan2f(static_cast<float>(ay), static_cast<float>(az)) *
            RAD_TO_DEG;
        float rawGyroRateXDps = gx / 131.0f;
        float gyroRateXDps = rawGyroRateXDps;
        bool gyroSpikeRejected = false;
        if (gyroHistoryCount >= 2) {
            gyroRateXDps = medianOfThree(
                rawGyroRateXDps,
                previousGyroRateDps,
                olderGyroRateDps
            );
            gyroSpikeRejected =
                fabsf(rawGyroRateXDps - gyroRateXDps) >=
                Config::GYRO_SPIKE_DIFFERENCE_DPS;
        } else {
            gyroHistoryCount++;
        }
        olderGyroRateDps = previousGyroRateDps;
        previousGyroRateDps = rawGyroRateXDps;

        float accelXG = ax / 16384.0f;
        float accelYG = ay / 16384.0f;
        float accelZG = az / 16384.0f;
        float accelNormG = sqrtf(
            accelXG * accelXG + accelYG * accelYG + accelZG * accelZG
        );

        if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(5))) {
            if (!filterInitialized) {
                filteredAngleDeg = accelAngleXDeg;
                filterInitialized = true;
            } else {
                float gyroPredictedAngleDeg =
                    filteredAngleDeg + gyroRateXDps * dtSec;
                bool accelTrusted =
                    accelNormG >= Config::ACCEL_TRUST_MIN_G &&
                    accelNormG <= Config::ACCEL_TRUST_MAX_G &&
                    fabsf(accelAngleXDeg - gyroPredictedAngleDeg) <=
                        Config::ACCEL_ANGLE_INNOVATION_LIMIT_DEG;
                float complementaryAlpha =
                    Config::COMPLEMENTARY_FILTER_TAU_SEC /
                    (Config::COMPLEMENTARY_FILTER_TAU_SEC + dtSec);
                filteredAngleDeg = accelTrusted
                    ? complementaryAlpha * gyroPredictedAngleDeg +
                          (1.0f - complementaryAlpha) * accelAngleXDeg
                    : gyroPredictedAngleDeg;
                balance.accelTrusted = accelTrusted;
            }

            balance.angleDeg = filteredAngleDeg - balance.angleOffsetDeg;
            balance.gyroRateDps = gyroRateXDps;
            balance.accelNormG = accelNormG;
            if (gyroSpikeRejected) {
                balance.gyroSpikeCount++;
            }
            balance.sensorUpdateMicros = micros();
            xSemaphoreGive(balanceMutex);
        }

        vTaskDelayUntil(
            &lastWake,
            pdMS_TO_TICKS(Config::SENSOR_LOOP_MS)
        );
    }
}

void TaskMotor(void *parameter) {
    writeMotorEsc(Config::ESC_NEUTRAL);
    Serial.println("-> [MOTOR Z] arming ESC at neutral for 5 seconds...");
    vTaskDelay(pdMS_TO_TICKS(Config::ESC_ARM_TIME_MS));

    uint32_t lastMicros = micros();
    int commandedEscAngle = Config::ESC_NEUTRAL;

    for (;;) {
        float dtSec = elapsedSeconds(
            &lastMicros,
            Config::CONTROL_DT_FALLBACK_SEC
        );
        int requestedEscAngle = Config::ESC_NEUTRAL;
        bool useAutoRamp = false;
        bool forceNeutral = false;

        if (xSemaphoreTake(balanceMutex, pdMS_TO_TICKS(10))) {
            uint32_t sensorAgeUs = micros() - balance.sensorUpdateMicros;
            bool sensorStale =
                balance.sensorUpdateMicros == 0 ||
                sensorAgeUs > Config::SENSOR_STALE_TIMEOUT_US;
            if (!balance.motorEnabled) {
                requestNeutralLocked();
                forceNeutral = true;
            } else if (balance.balanceEnabled) {
                if (!mpuReady || sensorStale ||
                    fabsf(balance.angleDeg) >
                        Config::BALANCE_ACTIVE_ANGLE_DEG) {
                    requestNeutralLocked();
                    balance.fault = true;
                    forceNeutral = true;
                } else {
                    useAutoRamp = true;
                    float gyroAlpha = dtSec /
                        (Config::GYRO_FILTER_TAU_SEC + dtSec);
                    balance.filteredGyroRateDps +=
                        gyroAlpha *
                        (balance.gyroRateDps -
                         balance.filteredGyroRateDps);

                    float errorDeg =
                        balance.targetAngleDeg - balance.angleDeg;
                    float command = 0.0f;
                    bool nearUpright =
                        fabsf(errorDeg) <= Config::ANGLE_DEADBAND_DEG &&
                        fabsf(balance.filteredGyroRateDps) <=
                            Config::GYRO_DEADBAND_DPS;
                    if (nearUpright) {
                        balance.proportionalTerm = 0.0f;
                        balance.integralTerm = 0.0f;
                        balance.derivativeTerm = 0.0f;
                        balance.outputCommand = 0.0f;
                        balance.outputSaturated = false;
                        balance.saturationTimeSec = 0.0f;
                    } else {
                        command = computeBalancePidLocked(
                            errorDeg,
                            balance.filteredGyroRateDps,
                            dtSec
                        );
                        balance.outputSaturated =
                            fabsf(command) >=
                            (Config::COMMAND_LIMIT - 0.5f);
                        if (balance.outputSaturated) {
                            balance.saturationTimeSec += dtSec;
                        } else {
                            balance.saturationTimeSec = 0.0f;
                        }
                    }

                    float directedCommand = constrain(
                        command * balance.motorDirection,
                        -Config::COMMAND_LIMIT,
                        Config::COMMAND_LIMIT
                    );
                    requestedEscAngle = commandToEscAngle(
                        directedCommand,
                        balance.outputLimitDeg,
                        balance.minOutputDeg
                    );
                }
            } else {
                requestedEscAngle = balance.manualEscAngle;
                balance.outputCommand = 0.0f;
                balance.outputSaturated = false;
                balance.saturationTimeSec = 0.0f;
            }

            if (balance.forceNeutral) {
                forceNeutral = true;
                balance.forceNeutral = false;
            }

            if (forceNeutral) {
                commandedEscAngle = Config::ESC_NEUTRAL;
            } else {
                int rampStep = useAutoRamp
                    ? Config::ESC_AUTO_RAMP_STEP
                    : Config::ESC_MANUAL_RAMP_STEP;
                commandedEscAngle = rampEscAngle(
                    commandedEscAngle,
                    requestedEscAngle,
                    rampStep
                );
            }
            balance.escAngle = commandedEscAngle;
            xSemaphoreGive(balanceMutex);
        }

        writeMotorEsc(commandedEscAngle);
        // Explicitly block every cycle so CPU 0's idle task can feed the watchdog.
        vTaskDelay(pdMS_TO_TICKS(Config::CONTROL_LOOP_MS));
    }
}

void TaskBluetooth(void *parameter) {
    bool wasConnected = bluetoothReady && SerialBT.connected();

    for (;;) {
        bool isConnected = bluetoothReady && SerialBT.connected();
        if (isConnected != wasConnected) {
            refreshBluetoothConnection();
            wasConnected = isConnected;
        }

        if (Serial.available() > 0) {
            handleCommand(Serial.readStringUntil('\n'));
        }

        if (isConnected && SerialBT.available() > 0) {
            handleCommand(SerialBT.readStringUntil('\n'));
        }

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

void setup() {
    Serial.begin(115200);
    Serial.setTimeout(50);
    delay(200);
    Serial.println("\n[1/6] Starting single-axis balancing cube...");

    pinMode(Config::CHECK_LED_PIN, OUTPUT);
    digitalWrite(Config::CHECK_LED_PIN, HIGH);

    ledMutex = xSemaphoreCreateMutex();
    balanceMutex = xSemaphoreCreateMutex();
    if (ledMutex == nullptr || balanceMutex == nullptr) {
        Serial.println("-> Fatal: mutex allocation failed.");
        while (true) {
            delay(1000);
        }
    }

    recoverI2CBus();
    mpuReady = initializeMpu();

    Serial.println("[4/6] Starting Z motor ESC...");
    ESP32PWM::allocateTimer(1);
    motorEsc.setPeriodHertz(50);
    motorEsc.attach(
        Config::MOTOR_Z_PIN,
        Config::ESC_MIN_US,
        Config::ESC_MAX_US
    );
    writeMotorEsc(Config::ESC_NEUTRAL);

    Serial.println("[5/6] Starting Bluetooth and NeoPixel...");
    SerialBT.setTimeout(50);
    bluetoothReady = SerialBT.begin(Config::BT_DEVICE_NAME, false);
    refreshBluetoothConnection();
    printBluetoothStatus();

    strip.begin();
    strip.setBrightness(100);
    strip.show();

    Serial.println("[6/6] Creating FreeRTOS tasks...");
    xTaskCreatePinnedToCore(TaskLed, "TaskLed", 4096, NULL, 1, NULL, 1);
    xTaskCreatePinnedToCore(TaskSensor, "TaskSensor", 4096, NULL, 2, NULL, 1);
    xTaskCreatePinnedToCore(
        TaskBluetooth,
        "TaskBluetooth",
        8192,
        NULL,
        1,
        NULL,
        1
    );
    xTaskCreatePinnedToCore(TaskMotor, "TaskMotor", 4096, NULL, 3, NULL, 0);

    Serial.println("--- Setup complete ---");
    printHelp();
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(1000));
}
