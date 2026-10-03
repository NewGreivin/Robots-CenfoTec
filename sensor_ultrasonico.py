import board
from hcsr04 import HCSR04

sonar = HCSR04(board.IO25, board.IO26)

def medir_distancia():
    try:
        dist = sonar.dist_cm()
        return dist if dist is not None else 999
    except Exception:
        return 999

def hay_obstaculo(distancia_minima_cm=15):
    return medir_distancia() < distancia_minima_cm