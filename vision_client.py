import socketpool
import wifi
import json
import time

class ClienteVision:
    def __init__(self, ip, puerto):
        self.ip           = ip
        self.puerto       = puerto
        self.pool         = socketpool.SocketPool(wifi.radio)
        self.sock         = None
        self.buffer_str   = ""
        self.buffer_bytes = bytearray(512)  # Reducido para ahorrar RAM
        self.conectado    = False

    def conectar(self, reintentos=10, pausa=3):
        self.conectado = False
        for intento in range(1, reintentos + 1):
            try:
                print(f"Intento {intento}/{reintentos} conectando a {self.ip}:{self.puerto}...")
                self.sock = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM)
                self.sock.settimeout(5)
                self.sock.connect((self.ip, self.puerto))
                self.sock.setblocking(False)
                self.conectado = True
                self.buffer_str = "" # Limpiar al conectar
                print("Conectado a la vision!")
                return True
            except Exception as e:
                print(f"Fallo: {e}. Reintentando en {pausa}s...")
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
                time.sleep(pausa)
        print("No se pudo conectar a la vision.")
        return False

    def leer_ultimo_estado(self):
        if not self.conectado or self.sock is None:
            return None
            
        try:
            # Leer datos del socket de forma segura
            while True:
                num_bytes = self.sock.recv_into(self.buffer_bytes)
                if num_bytes == 0:
                    print("Conexion con vision perdida.")
                    self.conectado = False
                    self.sock = None
                    return None
                
                # Evitar desbordamiento de memoria limitando el tamaño del búfer acumulado
                if len(self.buffer_str) > 2048:
                    self.buffer_str = self.buffer_str[-1024:] # Descartar lo más viejo
                    
                self.buffer_str += self.buffer_bytes[:num_bytes].decode('utf-8')
        except OSError:
            pass

        if not "\n" in self.buffer_str:
            return None

        lineas = self.buffer_str.split('\n')
        self.buffer_str = lineas.pop() # Dejar la última línea incompleta en el búfer

        # Buscar el estado más reciente analizando desde el final hacia atrás
        for linea in reversed(lineas):
            linea = linea.strip()
            if linea:
                try:
                    return json.loads(linea)
                except ValueError:
                    pass
        return None