import cv2
import json
import time
import threading
import random
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

# Importar logs-generator
sys.path.insert(0, os.path.dirname(__file__))
try:
    import importlib
    logs_generator = importlib.import_module('logs-generator')
    LogGenerator = logs_generator.LogGenerator
    
    # Inicializar sistema de logs
    LogGenerator(log_dir="logs", log_file="rtsp-connections.log", console=True)
    logger = LogGenerator.get_logger(__name__)
except ImportError as e:
    # Fallback si no existe logs-generator
    print(f"⚠️  No se pudo importar logs-generator: {e}")
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class RTSPConnectionManager:
    """
    Gestor de conexiones RTSP con reconexión automática.
    Mantiene y monitorea múltiples streams RTSP, reconectando automáticamente
    las conexiones perdidas.
    """
    
    def __init__(self, json_path: str, check_interval: int = 30, max_retries: int = 3, 
                 connection_timeout: int = 5, read_timeout: int = 10, backoff_max: int = 60):
        """
        Inicializar el gestor de conexiones.
        
        Args:
            json_path: Ruta al archivo JSON con las URIs RTSP
            check_interval: Intervalo en segundos para verificar conexiones (default: 30)
            max_retries: Número máximo de intentos de reconexión (default: 3)
            connection_timeout: Timeout de conexión FFmpeg en segundos (default: 5)
            read_timeout: Timeout de lectura FFmpeg en segundos (default: 10)
            backoff_max: Backoff máximo en segundos para reconexión (default: 60)
        """
        self.json_path = json_path
        self.check_interval = check_interval
        self.max_retries = max_retries
        self.connection_timeout = connection_timeout * 1000000  # Convertir a microsegundos
        self.read_timeout = read_timeout * 1000000
        self.backoff_max = backoff_max
        
        # Diccionario para almacenar las conexiones activas
        # Formato: {uri: {
        #   "cap": VideoCapture, 
        #   "status": str, 
        #   "retries": int, 
        #   "last_check": datetime,
        #   "last_frame_time": datetime,  # Para heartbeat
        #   "backoff": int,  # Backoff actual en segundos
        #   "next_retry_time": datetime,  # Cuándo reintentar
        #   "closing": bool  # Bandera de cierre
        # }}
        self.connections: Dict[str, dict] = {}
        
        # Control del thread de monitoreo
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Lock para operaciones thread-safe (usar solo para operaciones rápidas)
        self.lock = threading.Lock()
        
        # Cargar URIs del archivo JSON
        self.uris = self._load_uris()
        
        logger.info(f"RTSPConnectionManager iniciado: {len(self.uris)} URIs")
        
    def _load_uris(self) -> list:
        """Cargar las URIs desde el archivo JSON."""
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                uris = data.get("URIS_LIST", [])
                return uris
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.json_path}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {self.json_path}: {e}")
            return []
    
    def _add_rtsp_options(self, uri: str) -> str:
        """
        Agregar opciones de FFmpeg a la URI RTSP para timeouts y estabilidad.
        
        Args:
            uri: URI original
            
        Returns:
            URI con opciones agregadas
        """
        # Si ya tiene parámetros, agregar con &, sino con ?
        separator = "&" if "?" in uri else "?"
        
        options = [
            "rtsp_transport=tcp",  # Usar TCP en lugar de UDP (más estable)
            f"stimeout={self.connection_timeout}",  # Socket/connection timeout
            f"timeout={self.read_timeout}",  # Read timeout
        ]
        
        return f"{uri}{separator}{('&'.join(options))}"
    
    def _connect_to_stream(self, uri: str) -> Optional[cv2.VideoCapture]:
        """
        Conectar a un stream RTSP individual.
        
        Args:
            uri: URI del stream RTSP
            
        Returns:
            VideoCapture object si la conexión es exitosa, None en caso contrario
        """
        try:
            print(f"🎥 Conectando a: {uri}")
            
            # Agregar opciones de timeout a la URI
            uri_with_options = self._add_rtsp_options(uri)
            
            # Abrir la conexión RTSP usando FFmpeg
            cap = cv2.VideoCapture(uri_with_options, cv2.CAP_FFMPEG)
            
            # Configurar buffer mínimo para baja latencia
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Verificar que la conexión se abrió correctamente
            if not cap.isOpened():
                print(f"❌ No se pudo abrir: {uri}")
                logger.warning(f"Connection failed: {uri}")
                return None
            
            # Intentar leer un frame de prueba para validar la conexión
            ret, _ = cap.read()
            if not ret:
                print(f"❌ Sin frames de: {uri}")
                logger.warning(f"No frames from: {uri}")
                cap.release()
                return None
            
            print(f"✅ Conectado: {uri}")
            logger.info(f"Connected: {uri}")
            return cap
            
        except Exception as e:
            logger.error(f"Connection error [{uri}]: {e}")
            return None
    
    def initialize_all_connections(self):
        """Inicializar todas las conexiones RTSP desde el archivo JSON."""
        print(f"\n{'='*60}")
        print(f"🚀 Inicializando conexiones RTSP...")
        print(f"{'='*60}\n")
        
        for uri in self.uris:
            cap = self._connect_to_stream(uri)
            
            now = datetime.now()
            with self.lock:
                if cap is not None:
                    self.connections[uri] = {
                        "cap": cap,
                        "status": "connected",
                        "retries": 0,
                        "last_check": now,
                        "last_frame_time": now,
                        "backoff": 1,
                        "next_retry_time": now,
                        "closing": False
                    }
                else:
                    self.connections[uri] = {
                        "cap": None,
                        "status": "disconnected",
                        "retries": 0,
                        "last_check": now,
                        "last_frame_time": None,
                        "backoff": 1,
                        "next_retry_time": now,
                        "closing": False
                    }
        
        # Resumen de conexiones
        with self.lock:
            connected = sum(1 for c in self.connections.values() if c["status"] == "connected")
            total = len(self.connections)
        
        print(f"\n📊 Resumen: {connected}/{total} cámaras conectadas")
        print(f"{'='*60}\n")
        logger.info(f"Initialized: {connected}/{total} cameras connected")
    
    def _check_connection_health(self, uri: str, heartbeat_timeout: int = 60) -> bool:
        """
        Verificar si una conexión está saludable SIN consumir frames.
        
        Usa heartbeat: verifica cuándo fue el último frame leído por el consumidor.
        
        Args:
            uri: URI del stream a verificar
            heartbeat_timeout: Segundos sin frames antes de considerar muerta (default: 60)
            
        Returns:
            True si la conexión está saludable, False en caso contrario
        """
        with self.lock:
            if uri not in self.connections:
                return False
            
            conn = self.connections[uri]
            cap = conn["cap"]
            
            # Si no hay objeto VideoCapture, la conexión está caída
            if cap is None:
                return False
            
            # Si está marcada para cierre, no es saludable
            if conn.get("closing", False):
                return False
            
            # Verificar si el objeto está abierto (sin leer frames)
            try:
                if not cap.isOpened():
                    return False
            except Exception as e:
                logger.error(f"Health check error [{uri}]: {e}")
                return False
            
            # Verificar heartbeat: ¿hace cuánto llegó el último frame?
            last_frame_time = conn.get("last_frame_time")
            if last_frame_time is None:
                # Nunca ha recibido frames, dar un poco de tiempo
                init_time = conn.get("last_check", datetime.now())
                if (datetime.now() - init_time).total_seconds() > heartbeat_timeout:
                    logger.warning(f"Heartbeat timeout [{uri}]: no frames after {heartbeat_timeout}s")
                    return False
            else:
                # Verificar si hace mucho que no llegan frames
                elapsed = (datetime.now() - last_frame_time).total_seconds()
                if elapsed > heartbeat_timeout:
                    logger.warning(f"Heartbeat timeout [{uri}]: {elapsed:.1f}s without frames")
                    return False
        
        return True
    
    def update_frame_heartbeat(self, uri: str):
        """
        Actualizar el timestamp del último frame recibido (heartbeat).
        Debe ser llamado por el thread/worker que lee frames.
        
        Args:
            uri: URI del stream
        """
        with self.lock:
            if uri in self.connections:
                self.connections[uri]["last_frame_time"] = datetime.now()
    
    def _attempt_reconnection(self, uri: str):
        """
        Intentar reconectar a un stream RTSP con backoff exponencial.
        
        Args:
            uri: URI del stream a reconectar
        """
        now = datetime.now()
        
        with self.lock:
            conn = self.connections[uri]
            
            # Verificar si aún no es tiempo de reintentar (backoff)
            if now < conn["next_retry_time"]:
                remaining = (conn["next_retry_time"] - now).total_seconds()
                logger.debug(f"[{uri}] Backoff activo, reintento en {remaining:.1f}s")
                return
            
            # Verificar si se excedió el número de reintentos
            if conn["retries"] >= self.max_retries:
                if conn["status"] != "failed":
                    logger.error(f"[{uri}] Máximo de reintentos alcanzado ({self.max_retries})")
                    conn["status"] = "failed"
                return
            
            # Marcar como closing antes de liberar
            conn["closing"] = True
            
            # Liberar la conexión anterior si existe
            if conn["cap"] is not None:
                try:
                    conn["cap"].release()
                except Exception as e:
                    logger.warning(f"[{uri}] Error al liberar cap: {e}")
            
            conn["retries"] += 1
            current_backoff = conn["backoff"]
            
            print(f"🔄 [{uri}] Reintento {conn['retries']}/{self.max_retries} (backoff: {current_backoff}s)")
            logger.info(f"Reconnect attempt [{uri}]: {conn['retries']}/{self.max_retries} backoff={current_backoff}s")
        
        # Intentar reconectar (fuera del lock para evitar bloqueos largos)
        cap = self._connect_to_stream(uri)
        
        with self.lock:
            conn = self.connections[uri]
            conn["closing"] = False  # Ya no está en proceso de cierre
            
            if cap is not None:
                # Reconexión exitosa
                conn["cap"] = cap
                conn["status"] = "connected"
                conn["retries"] = 0
                conn["backoff"] = 1
                conn["last_check"] = datetime.now()
                conn["last_frame_time"] = datetime.now()
                conn["next_retry_time"] = datetime.now()
                logger.info(f"Reconnected successfully: {uri}")
            else:
                # Reconexión fallida: calcular siguiente backoff
                conn["cap"] = None
                conn["status"] = "disconnected"
                conn["last_check"] = datetime.now()
                
                # Backoff exponencial: 1, 2, 4, 8, 16, 32, 60 (max)
                next_backoff = min(current_backoff * 2, self.backoff_max)
                
                # Agregar jitter aleatorio (±20%) para evitar thundering herd
                jitter = random.uniform(0.8, 1.2)
                backoff_with_jitter = int(next_backoff * jitter)
                
                conn["backoff"] = next_backoff
                conn["next_retry_time"] = datetime.now() + timedelta(seconds=backoff_with_jitter)
    
    def _monitor_loop(self):
        """Loop principal del thread de monitoreo."""
        print(f"👁️  Monitor iniciado (intervalo: {self.check_interval}s)")
        logger.info(f"Monitor started: interval={self.check_interval}s")
        
        while self.monitoring:
            time.sleep(self.check_interval)
            
            if not self.monitoring:
                break
            
            # Minimizar tiempo bajo lock: copiar URIs a verificar
            with self.lock:
                uris_to_check = list(self.connections.keys())
            
            for uri in uris_to_check:
                if not self.monitoring:
                    break
                
                is_healthy = self._check_connection_health(uri)
                
                if not is_healthy:
                    # Obtener estado actual sin sostener lock mucho tiempo
                    with self.lock:
                        if uri in self.connections:
                            status = self.connections[uri]["status"]
                        else:
                            continue
                    
                    if status == "connected":
                        print(f"⚠️  Conexión perdida: {uri}")
                        logger.warning(f"Connection lost: {uri}")
                        with self.lock:
                            if uri in self.connections:
                                self.connections[uri]["status"] = "disconnected"
                    
                    # Intentar reconectar
                    self._attempt_reconnection(uri)
            
            # Mostrar resumen
            with self.lock:
                connected = sum(1 for c in self.connections.values() if c["status"] == "connected")
                disconnected = sum(1 for c in self.connections.values() if c["status"] == "disconnected")
                failed = sum(1 for c in self.connections.values() if c["status"] == "failed")
            
            print(f"📊 Estado: ✅ {connected} | ⚠️  {disconnected} | 🚫 {failed}")
            # Solo registrar cambios significativos
            if disconnected > 0 or failed > 0:
                logger.warning(f"Status: connected={connected} disconnected={disconnected} failed={failed}")
    
    def start_monitoring(self):
        """Iniciar el thread de monitoreo de conexiones."""
        if self.monitoring:
            print("⚠️  El monitoreo ya está activo")
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Detener el thread de monitoreo de conexiones."""
        if not self.monitoring:
            return
        
        print("🛑 Deteniendo monitor...")
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Monitor stopped")
    
    def get_connection(self, uri: str) -> Optional[cv2.VideoCapture]:
        """
        Obtener la conexión VideoCapture para una URI específica.
        
        IMPORTANTE: Después de leer un frame exitosamente, llamar update_frame_heartbeat(uri)
        para mantener el sistema de monitoreo actualizado.
        
        Args:
            uri: URI del stream
            
        Returns:
            VideoCapture object si está conectado y no está cerrándose, None en caso contrario
        """
        with self.lock:
            if uri in self.connections:
                conn = self.connections[uri]
                if conn["status"] == "connected" and not conn.get("closing", False):
                    return conn["cap"]
            return None
    
    def get_all_active_connections(self) -> Dict[str, cv2.VideoCapture]:
        """
        Obtener todas las conexiones activas.
        
        IMPORTANTE: Después de leer frames, llamar update_frame_heartbeat(uri) para cada URI.
        
        Returns:
            Diccionario con URIs como keys y VideoCapture objects como values
        """
        with self.lock:
            return {
                uri: conn["cap"] 
                for uri, conn in self.connections.items() 
                if conn["status"] == "connected" and conn["cap"] is not None and not conn.get("closing", False)
            }
    
    def get_status_summary(self) -> dict:
        """Obtener un resumen del estado de todas las conexiones."""
        with self.lock:
            return {
                "total": len(self.connections),
                "connected": sum(1 for c in self.connections.values() if c["status"] == "connected"),
                "disconnected": sum(1 for c in self.connections.values() if c["status"] == "disconnected"),
                "failed": sum(1 for c in self.connections.values() if c["status"] == "failed"),
                "details": {
                    uri: {
                        "status": conn["status"],
                        "retries": conn["retries"],
                        "backoff": conn["backoff"],
                        "last_check": conn["last_check"].strftime('%Y-%m-%d %H:%M:%S'),
                        "last_frame": conn["last_frame_time"].strftime('%Y-%m-%d %H:%M:%S') if conn["last_frame_time"] else "Never",
                        "next_retry": conn["next_retry_time"].strftime('%Y-%m-%d %H:%M:%S') if conn["status"] == "disconnected" else "N/A"
                    }
                    for uri, conn in self.connections.items()
                }
            }
    
    def close_all_connections(self):
        """Cerrar todas las conexiones y liberar recursos."""
        print("\n🛑 Cerrando conexiones RTSP...")
        
        self.stop_monitoring()
        
        closed_count = 0
        errors = 0
        with self.lock:
            for uri, conn in self.connections.items():
                if conn["cap"] is not None:
                    try:
                        conn["closing"] = True
                        conn["cap"].release()
                        closed_count += 1
                    except Exception as e:
                        logger.error(f"Error closing [{uri}]: {e}")
                        errors += 1
            
            self.connections.clear()
        
        print(f"✅ {closed_count} conexiones cerradas")
        logger.info(f"Closed {closed_count} connections" + (f", {errors} errors" if errors > 0 else ""))


# Función legacy para compatibilidad con código antiguo
def ConnectToRTSPStream(uri: str) -> cv2.VideoCapture:
    """
    Conectar a un stream RTSP individual (función legacy).
    
    Args:
        uri: URI del stream RTSP
        
    Returns:
        VideoCapture object configurado
        
    Raises:
        RuntimeError: Si no se puede abrir la fuente RTSP
    """
    print(f"Conectando a fuente de video RTSP: {uri}")
    
    # Abrir la conexión RTSP usando FFmpeg para decodificar
    cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
    
    # Reducir el buffer a 1 frame para minimizar el retraso (latencia)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Verificar que la fuente de video se abrió correctamente
    if not cap.isOpened():
        raise RuntimeError(f"❌ No se pudo abrir la fuente RTSP: {uri}")
    
    return cap