import board
import neopixel
import analogio
from time import sleep

# El LED iluminador está en el pin IO4
pixel_iluminador = neopixel.NeoPixel(board.IO4, 1, brightness=1, auto_write=True)
# El sensor lee en el pin IO32
luz = analogio.AnalogIn(board.IO32)

def _medir_con_color(color_rgb):
    pixel_iluminador[0] = (0, 0, 0)
    sleep(0.03)

    pixel_iluminador[0] = color_rgb
    sleep(0.15) # Tiempo óptimo de estabilización sin parpadeo largo

    total = 0
    muestras = 10
    for _ in range(muestras):
        total += luz.value
        sleep(0.002)

    pixel_iluminador[0] = (0, 0, 0)
    return total / muestras

def detectar_color():
    # Medición rápida y limpia de los 3 canales
    rojo_raw  = _medir_con_color((255, 0, 0))
    verde_raw = _medir_con_color((0, 255, 0))
    azul_raw  = _medir_con_color((0, 0, 255))

    print(f"Lecturas sensor color -> R:{int(rojo_raw)} G:{int(verde_raw)} B:{int(azul_raw)}")

    if rojo_raw > verde_raw and rojo_raw > azul_raw:
        return "red"
    elif verde_raw > rojo_raw and verde_raw > azul_raw:
        return "green"
    elif azul_raw > rojo_raw and azul_raw > verde_raw:
        return "blue"
    else:
        if rojo_raw >= verde_raw:
            return "red"
        return "green"

def encender_led_permanente(color_name):
    """Mantiene el LED encendido del color exacto del cubo detectado"""
    if color_name == "red":
        pixel_iluminador[0] = (255, 0, 0)
    elif color_name == "green":
        pixel_iluminador[0] = (0, 255, 0)
    elif color_name == "blue":
        pixel_iluminador[0] = (0, 0, 255)

def apagar_led():
    pixel_iluminador[0] = (0, 0, 0)