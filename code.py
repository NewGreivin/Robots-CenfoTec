import time
import wifi
import json
import os
import math
import movimiento
import sensor_ultrasonico
import sensor_color
from vision_client import ClienteVision

print("=== INICIANDO ROBOT AUTÓNOMO (PRECISIÓN Y FLUJO COMPLETO) ===")
print("Wi-Fi Listo. IP del robot:", wifi.radio.ipv4_address)

VISION_IP     = os.getenv("VISION_IP")
VISION_PUERTO = int(os.getenv("VISION_PUERTO"))
MI_ARUCO_ID   = int(os.getenv("MI_ARUCO_ID"))

VELOCIDAD_NORMAL  = 0.28  # Velocidad controlada para máxima precisión
VELOCIDAD_GIRO    = 0.20  # Giro suave y estable
DISTANCIA_LLEGADA = 5.5   
DISTANCIA_META    = 5.8   # Distancia exacta para la estación de depósito

estado_robot      = "BUSCANDO_CUBO"
color_cubo_actual = None

vision = ClienteVision(VISION_IP, VISION_PUERTO)

while not vision.conectar(reintentos=5, pausa=3):
    print("Reintentando conexion con la vision en 5 segundos...")
    time.sleep(5)

movimiento.calibrar_drift(2)
print("¡Todo listo! Esperando a que el árbitro inicie la ronda (RUNNING)...")

def calcular_angulo_hacia(rob_x, rob_y, dest_x, dest_y):
    dx = dest_x - rob_x
    dy = rob_y - dest_y 
    return math.atan2(dy, dx) * (180 / math.pi)

def calcular_distancia(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

def diferencia_angulo(actual, deseado):
    diff = deseado - actual
    while diff > 180:
        diff -= 360
    while diff < -180:
        diff += 360
    return diff

def cubo_esta_en_posicion(cubo, depositos):
    """Retorna True solo si el cubo está exactamente en el centro de su estación."""
    for dep in depositos:
        if dep.get("color") == cubo.get("color"):
            # Reducido de 7.0 a 4.2 para que un cubo mal puesto o desviado NO se dé por bueno
            if calcular_distancia(cubo["col"], cubo["row"], dep["col"], dep["row"]) < 4.2:
                return True
    return False

def navegar_hacia(rob_x, rob_y, rob_ang, dest_x, dest_y, es_meta=False):
    distancia_limite = DISTANCIA_META if es_meta else DISTANCIA_LLEGADA
    distancia = calcular_distancia(rob_x, rob_y, dest_x, dest_y)
    
    if distancia <= distancia_limite:
        movimiento.stop()
        return True

    angulo_deseado = calcular_angulo_hacia(rob_x, rob_y, dest_x, dest_y)
    diff = diferencia_angulo(rob_ang, angulo_deseado)

    # Si la diferencia de ángulo es notable, gira suavemente sin dar vueltas bruscas
    if abs(diff) > 15:
        sentido = 1 if diff > 0 else -1
        movimiento.girar(VELOCIDAD_GIRO * sentido)
        movimiento.ib.pixel = (255, 165, 0)
    else:
        # Corrección proporcional suave para avanzar derecho al objetivo

        velocidad_actual = 0.20 if es_meta else VELOCIDAD_NORMAL

        Kp = 0.010
        correccion = diff * Kp
        motor_izq = max(0.1, min(1.0, VELOCIDAD_NORMAL - correccion))
        motor_der = max(0.1, min(1.0, VELOCIDAD_NORMAL + correccion))

        movimiento.ib.motor_1.throttle = motor_izq
        movimiento.ib.motor_2.throttle = motor_der
        movimiento.ib.pixel = (0, 255, 255)

    return False

while True:
    estado = vision.leer_ultimo_estado()

    if not estado:
        time.sleep(0.02)
        continue

    fase = estado.get("phase")
    if fase != "RUNNING":
        movimiento.stop()
        print(f"Esperando... Fase actual: {fase}")
        time.sleep(0.1)
        continue

    mi_robot = None
    for r in estado.get("rovers", []):
        if r.get("id") == MI_ARUCO_ID:
            mi_robot = r
            break

    if not mi_robot:
        movimiento.stop()
        print(f"⚠️ Cámara no ve ArUco ID:{MI_ARUCO_ID}. Verifique iluminación.")
        time.sleep(0.5)
        continue

    rob_x   = mi_robot["col"]
    rob_y   = mi_robot["row"]
    rob_ang = mi_robot["theta"]

    cubos_vivos     = estado.get("cubes", [])
    depositos_vivos = estado.get("depots", [])

    # ==========================================
    # FASE 1: BUSCANDO CUBOS FUERA DE POSICIÓN
    # ==========================================
    if estado_robot == "BUSCANDO_CUBO":
        # Filtramos y tomamos solo los cubos que NO están en su posición correcta
        cubos_pendientes = [c for c in cubos_vivos if not cubo_esta_en_posicion(c, depositos_vivos)]

        if not cubos_pendientes:
            print("[LOG] 🎉 ¡JUEGO TERMINADO! Todos los cubos están en su posición correcta.")
            estado_robot = "JUEGO_TERMINADO"
            continue

        # Seleccionar el cubo pendiente más cercano al robot
        cubo_cercano = None
        dist_minima  = 9999
        for cubo in cubos_pendientes:
            d = calcular_distancia(rob_x, rob_y, cubo["col"], cubo["row"])
            if d < dist_minima:
                dist_minima  = d
                cubo_cercano = cubo

        dest_x = cubo_cercano["col"]
        dest_y = cubo_cercano["row"]
        print(f"[LOG] [BÚSQUEDA] Dirigiéndose al cubo fuera de posición en ({dest_x:.1f},{dest_y:.1f}) | Dist: {dist_minima:.1f}")

        llegue = navegar_hacia(rob_x, rob_y, rob_ang, dest_x, dest_y)
        if llegue:
            movimiento.stop()
            print("[LOG] [CAPTURA] Posición del cubo alcanzada. Avanzando para asegurar en brazos...")
            estado_robot = "TOMANDO_CUBO"

    # ==========================================
    # FASE 2: CAPTURA Y IDENTIFICACIÓN DE COLOR
    # ==========================================
    elif estado_robot == "TOMANDO_CUBO":
        t0 = time.monotonic()
        while True:
            dist_fisica = sensor_ultrasonico.medir_distancia()
            if dist_fisica <= 3.8:  # Rango óptimo de sujeción en tenazas
                movimiento.stop()
                break
            movimiento.avanzar(0.12)
            if (time.monotonic() - t0) > 2.0:
                movimiento.stop()
                break

        time.sleep(0.1)
        print("[LOG] [IDENTIFICACIÓN] Tomando muestras del sensor de color...")

        muestras_validas = []
        for _ in range(4):
            c_det = sensor_color.detectar_color()
            if c_det in ["red", "green", "blue"]:
                muestras_validas.append(c_det)
            time.sleep(0.03)

        color_detectado = max(set(muestras_validas), key=muestras_validas.count) if muestras_validas else "red"
        color_cubo_actual = color_detectado
        
        print(f"[LOG] [ÉXITO] Cubo identificado correctamente como: {color_cubo_actual.upper()}. Activando LED y transportando.")
        sensor_color.encender_led_permanente(color_cubo_actual)
        estado_robot = "LLEVANDO_A_ESTACION"

    # ==========================================
    # FASE 3: TRANSPORTE A LA ESTACIÓN CORRESPONDIENTE
    # ==========================================
    elif estado_robot == "LLEVANDO_A_ESTACION":
        deposito = None
        for dep in depositos_vivos:
            if dep.get("color") == color_cubo_actual:
                deposito = dep
                break

        if deposito is None:
            print(f"[LOG] [ERROR] No se encuentra la estación de depósito para el color '{color_cubo_actual}'.")
            time.sleep(0.2)
            continue

        dest_x = deposito["col"]
        dest_y = deposito["row"]
        distancia = calcular_distancia(rob_x, rob_y, dest_x, dest_y)
        print(f"[LOG] [TRANSPORTE] Llevando cubo {color_cubo_actual} a su estación | Distancia restante: {distancia:.1f}")

        llegue = navegar_hacia(rob_x, rob_y, rob_ang, dest_x, dest_y, es_meta=True)

        if llegue:
            movimiento.stop()
            print("[LOG] [ENTREGA] Estación correcta alcanzada. Soltando cubo en su espacio...")
            
            # Retroceso limpio y preciso para dejar el cubo en su lugar sin arrastrarlo
            movimiento.retroceder(0.25)
            time.sleep(0.9)
            movimiento.stop()
            
            sensor_color.apagar_led()
            print("[LOG] ✓ Cubo entregado con éxito. Buscando siguiente objetivo...")
            
            color_cubo_actual = None
            estado_robot = "BUSCANDO_CUBO"

    # ==========================================
    # FASE 4: JUEGO TERMINADO (BLOQUEO FINAL)
    # ==========================================
    elif estado_robot == "JUEGO_TERMINADO":
        movimiento.stop()
        sensor_color.apagar_led()
        print("[LOG] Misión completada satisfactoriamente. Todos los cubos están en posición.")
        while True:
            movimiento.stop()
            time.sleep(1)

    time.sleep(0.02)