import time
import wifi
import json
import os
import math
import espnow  # Importamos ESP-NOW para la comunicación
import movimiento
import sensor_ultrasonico
import sensor_color
from vision_client import ClienteVision

print("=== INICIANDO ROBOT AUTÓNOMO (PRECISIÓN Y FLUJO COMPLETO) ===")
print("Wi-Fi Listo. IP del robot:", wifi.radio.ipv4_address)

VISION_IP     = os.getenv("VISION_IP")
VISION_PUERTO = int(os.getenv("VISION_PUERTO"))
MI_ARUCO_ID   = int(os.getenv("MI_ARUCO_ID"))

# ==========================================
# CONFIGURACIÓN ESP-NOW
# ==========================================
PEER_MAC_STR = os.getenv("PEER_MAC", "FF:FF:FF:FF:FF:FF")
CANAL_ESPNOW = 6

try:
    # Iniciar AP brevemente para fijar el canal Wi-Fi
    wifi.radio.start_ap(" ", "", channel=CANAL_ESPNOW, max_connections=0)
    wifi.radio.stop_ap()
    
    esp = espnow.ESPNow()
    
    def mac_from_string(mac_string):
        return bytes(int(part, 16) for part in mac_string.split(":"))
        
    peer_mac_bytes = mac_from_string(PEER_MAC_STR)
    peer = espnow.Peer(mac=peer_mac_bytes, channel=CANAL_ESPNOW)
    esp.peers.append(peer)
    
    mi_mac = ":".join("{:02X}".format(b) for b in wifi.radio.mac_address)
    print(f"ESP-NOW Listo. Mi MAC: {mi_mac}")
    print(f"Emparejado con robot: {PEER_MAC_STR}")
except Exception as e:
    print("Error iniciando ESP-NOW:", e)
    esp = None

# Variables para guardar lo que nos dice el otro robot
estado_otro_robot = "DESCONOCIDO"
objetivo_otro_robot = None  # Guardará (x, y) del cubo al que va el otro robot

def enviar_mensaje_espnow(comando, datos):
    if esp is None: return
    msg = f"{MI_ARUCO_ID}|{comando}|{datos}"
    try:
        esp.send(msg.encode("utf-8"), peer)
    except:
        pass

def procesar_mensajes_espnow():
    global estado_otro_robot, objetivo_otro_robot
    if esp is None: return
    
    while True:
        packet = esp.read()
        if packet is None: break
        try:
            msg = packet.msg.decode("utf-8")
            partes = msg.split("|")
            if len(partes) >= 3:
                sender_id = partes[0]
                comando = partes[1]
                datos = partes[2]
                
                if comando == "TARGET":
                    coords = datos.split(",")
                    objetivo_otro_robot = (float(coords[0]), float(coords[1]))
                elif comando == "STATE":
                    estado_otro_robot = datos
        except Exception:
            pass
# ==========================================

VELOCIDAD_NORMAL  = 0.28
VELOCIDAD_GIRO    = 0.20
DISTANCIA_LLEGADA = 5.5   
DISTANCIA_META    = 7.0
DISTANCIA_COLISION = 7.0

estado_robot      = "BUSCANDO_CUBO"
estado_anterior   = "" # Para enviar actualización solo cuando cambiamos de fase
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
    while diff > 180: diff -= 360
    while diff < -180: diff += 360
    return diff

def cubo_esta_en_posicion(cubo, depositos):
    for dep in depositos:
        if dep.get("color") == cubo.get("color"):
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

    if abs(diff) > 15:
        sentido = 1 if diff > 0 else -1
        movimiento.girar(VELOCIDAD_GIRO * sentido)
        movimiento.ib.pixel = (255, 165, 0)
    else:
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
    # Leer mensajes de radio que hayan llegado
    procesar_mensajes_espnow()
    
    # Avisar al otro robot si cambiamos de estado
    if estado_robot != estado_anterior:
        enviar_mensaje_espnow("STATE", estado_robot)
        estado_anterior = estado_robot

    estado = vision.leer_ultimo_estado()

    if not estado:
        time.sleep(0.02)
        continue

    fase = estado.get("phase")
    if fase != "RUNNING":
        movimiento.stop()
        time.sleep(0.1)
        continue

    mi_robot = None
    otro_robot = None
    
    for r in estado.get("rovers", []):
        if r.get("id") == MI_ARUCO_ID:
            mi_robot = r
        else:
            otro_robot = r

    if not mi_robot:
        movimiento.stop()
        print(f"⚠️ Cámara no ve ArUco ID:{MI_ARUCO_ID}. Verifique iluminación.")
        time.sleep(0.5)
        continue

    rob_x   = mi_robot["col"]
    rob_y   = mi_robot["row"]
    rob_ang = mi_robot["theta"]

    # ==========================================
    # EVASIÓN FÍSICA DE COLISIONES
    # ==========================================
    if otro_robot:
        dist_robots = calcular_distancia(rob_x, rob_y, otro_robot["col"], otro_robot["row"])
        # Si los robots se acercan a menos de 7 cm
        if dist_robots < DISTANCIA_COLISION:
            if MI_ARUCO_ID > otro_robot.get("id", 0):
                movimiento.stop()
                print(f"[LOG] ⚠️ Compañero muy cerca ({dist_robots:.1f}). Cediendo el paso...")
                time.sleep(0.3)
                continue

    cubos_vivos     = estado.get("cubes", [])
    depositos_vivos = estado.get("depots", [])

    # ==========================================
    # FASE 1: BUSCANDO CUBOS FUERA DE POSICIÓN
    # ==========================================
    if estado_robot == "BUSCANDO_CUBO":
        cubos_pendientes = [c for c in cubos_vivos if not cubo_esta_en_posicion(c, depositos_vivos)]

        # Descartar el cubo que el otro robot ya está persiguiendo
        if objetivo_otro_robot is not None and estado_otro_robot in ["BUSCANDO_CUBO", "TOMANDO_CUBO"]:
            cubos_pendientes = [
                c for c in cubos_pendientes 
                if calcular_distancia(c["col"], c["row"], objetivo_otro_robot[0], objetivo_otro_robot[1]) > 4.0
            ]

        if not cubos_pendientes:
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
        
        # Avisar al compañero por ESP-NOW que vamos a ir por ESTE cubo específico
        enviar_mensaje_espnow("TARGET", f"{dest_x:.1f},{dest_y:.1f}")

        llegue = navegar_hacia(rob_x, rob_y, rob_ang, dest_x, dest_y)
        if llegue:
            movimiento.stop()
            estado_robot = "TOMANDO_CUBO"

    # ==========================================
    # FASE 2: CAPTURA Y IDENTIFICACIÓN DE COLOR
    # ==========================================
    elif estado_robot == "TOMANDO_CUBO":
        t0 = time.monotonic()
        while True:
            dist_fisica = sensor_ultrasonico.medir_distancia()
            if dist_fisica <= 3.8:
                movimiento.stop()
                break
            movimiento.avanzar(0.12)
            if (time.monotonic() - t0) > 2.0:
                movimiento.stop()
                break

        time.sleep(0.1)

        muestras_validas = []
        for _ in range(4):
            c_det = sensor_color.detectar_color()
            if c_det in ["red", "green", "blue"]:
                muestras_validas.append(c_det)
            time.sleep(0.03)

        color_detectado = max(set(muestras_validas), key=muestras_validas.count) if muestras_validas else "red"
        color_cubo_actual = color_detectado
        
        sensor_color.encender_led_permanente(color_cubo_actual)
        
        # Ya tomamos el cubo, limpiamos el objetivo para que el otro robot sepa que ya no está en el piso
        enviar_mensaje_espnow("TARGET", "0.0,0.0")
        estado_robot = "LLEVANDO_A_ESTACION"

    # ==========================================
    # FASE 3: TRANSPORTE A LA ESTACIÓN
    # ==========================================
    elif estado_robot == "LLEVANDO_A_ESTACION":
        deposito = None
        for dep in depositos_vivos:
            if dep.get("color") == color_cubo_actual:
                deposito = dep
                break

        if deposito is None:
            time.sleep(0.2)
            continue

        dest_x = deposito["col"]
        dest_y = deposito["row"]
        llegue = navegar_hacia(rob_x, rob_y, rob_ang, dest_x, dest_y, es_meta=True)

        if llegue:
            movimiento.stop()
            movimiento.retroceder(0.25)
            time.sleep(0.9)
            movimiento.stop()
            
            sensor_color.apagar_led()
            color_cubo_actual = None
            estado_robot = "BUSCANDO_CUBO"

    # ==========================================
    # FASE 4: JUEGO TERMINADO
    # ==========================================
    elif estado_robot == "JUEGO_TERMINADO":
        movimiento.stop()
        sensor_color.apagar_led()
        while True:
            movimiento.stop()
            time.sleep(1)

    time.sleep(0.02)