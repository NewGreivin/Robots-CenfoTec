import time
import board
import math
from ideaboard import IdeaBoard
from adafruit_lsm6ds.lsm6ds3trc import LSM6DS3TRC

RAD_A_GRADOS = 180 / math.pi
ib     = IdeaBoard()
i2c    = board.I2C()
sensor = LSM6DS3TRC(i2c, 0x6b)
drift_z = 0.0

def calibrar_drift(segundos=3):
    global drift_z
    print("Calibrando giroscopio...")
    suma, muestras = 0, 0
    t0 = time.monotonic()
    while (time.monotonic() - t0) < segundos:
        data = sensor.gyro[2]
        if abs(data) < 0.008:
            suma    += data
            muestras += 1
        time.sleep(0.005)
    drift_z = suma / muestras if muestras > 0 else 0
    print(f"Drift calibrado: {drift_z:.5f} rad/s")
    
MULT_M1 = 1
MULT_M2 = 1

def stop():
    ib.motor_1.throttle = 0
    ib.motor_2.throttle = 0

def avanzar(velocidad=0.5):
    velocidad = max(0.0, min(1.0, velocidad))
    ib.motor_1.throttle = velocidad * MULT_M1
    ib.motor_2.throttle = velocidad * MULT_M2

def retroceder(velocidad=0.5):
    velocidad = max(0.0, min(1.0, velocidad))
    ib.motor_1.throttle = -velocidad * MULT_M1
    ib.motor_2.throttle = -velocidad * MULT_M2

def girar(velocidad=0.3):
    velocidad = max(-1.0, min(1.0, velocidad))
    ib.motor_1.throttle = -velocidad * MULT_M1
    ib.motor_2.throttle = velocidad * MULT_M2