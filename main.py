"""
Sistema de Detección de Shoplifting con IA
Punto de entrada principal de la aplicación.

Flujo:
1. Inicializar gestor de conexiones RTSP
2. Iniciar monitoreo de conexiones
3. Loop principal de procesamiento:
   - Leer frames de cámaras activas
   - Actualizar heartbeat
   - Ejecutar inferencia (modelo de detección)
   - Generar alertas si se detecta shoplifting
   - Construir clips de evidencia
4. Cerrar conexiones al finalizar
"""

import sys
import os
import time
import cv2
import importlib
from datetime import datetime
from typing import Dict

# Agregar directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Importar módulos del sistema
rtsp_connection = importlib.import_module('rtsp-connection')
RTSPConnectionManager = rtsp_connection.RTSPConnectionManager

# Importar logs-generator
try:
    logs_generator = importlib.import_module('logs-generator')
    LogGenerator = logs_generator.LogGenerator
    LogGenerator(log_dir="logs", log_file="main.log", console=True)
    logger = LogGenerator.get_logger(__name__)
except ImportError as e:
    print(f"⚠️  No se pudo importar logs-generator: {e}")
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class ShopliftingDetectionSystem:
    """
    Sistema principal de detección de shoplifting.
    Orquesta todos los componentes: conexiones, inferencia, alertas, clips.
    """
    
    def __init__(self, config: dict):
        """
        Inicializar el sistema.
        
        Args:
            config: Diccionario con configuración del sistema
        """
        self.config = config
        
        # Inicializar gestor de conexiones RTSP
        self.rtsp_manager = RTSPConnectionManager(
            json_path=config.get('rtsp_uris_path', 'rtsp-uris.json'),
            check_interval=config.get('check_interval', 30),
            max_retries=config.get('max_retries', 5),
            connection_timeout=config.get('connection_timeout', 5),
            read_timeout=config.get('read_timeout', 10),
            backoff_max=config.get('backoff_max', 60)
        )
        
        # Placeholders para otros componentes (agregar después)
        self.inference_system = None  # TODO: Inicializar sistema de inferencia
        self.alert_emitter = None     # TODO: Inicializar emisor de alertas
        self.clip_constructor = None  # TODO: Inicializar constructor de clips
        
        # Control de ejecución
        self.running = False
        
        # Estadísticas
        self.stats = {
            'frames_processed': 0,
            'detections': 0,
            'alerts_sent': 0,
            'start_time': None
        }
        
        logger.info("ShopliftingDetectionSystem initialized")
    
    def initialize(self):
        """Inicializar todos los componentes del sistema."""
        print(f"\n{'='*70}")
        print("🚀 INICIALIZANDO SISTEMA DE DETECCIÓN DE SHOPLIFTING")
        print(f"{'='*70}\n")
        
        # 1. Inicializar conexiones RTSP
        print("📡 Inicializando conexiones RTSP...")
        self.rtsp_manager.initialize_all_connections()
        
        status = self.rtsp_manager.get_status_summary()
        print(f"✅ Cámaras: {status['connected']}/{status['total']} conectadas\n")
        logger.info(f"System initialized: {status['connected']}/{status['total']} cameras")
        
        # 2. Iniciar monitoreo de conexiones
        self.rtsp_manager.start_monitoring()
        
        # 3. Inicializar modelo de inferencia (TODO)
        # print("🧠 Cargando modelo de detección...")
        # self.inference_system = InferenceSystem(config=self.config)
        
        # 4. Inicializar emisor de alertas (TODO)
        # print("📢 Inicializando sistema de alertas...")
        # self.alert_emitter = AlertEmitter(config=self.config)
        
        # 5. Inicializar constructor de clips (TODO)
        # print("🎬 Inicializando constructor de clips...")
        # self.clip_constructor = ClipConstructor(config=self.config)
        
        print(f"{'='*70}")
        print("✅ Sistema inicializado correctamente")
        print(f"{'='*70}\n")
    
    def process_frame(self, uri: str, frame):
        """
        Procesar un frame individual.
        
        Args:
            uri: URI de la cámara
            frame: Frame de video (numpy array)
        
        Returns:
            Dict con resultados del procesamiento
        """
        result = {
            'uri': uri,
            'timestamp': datetime.now(),
            'detections': [],
            'should_alert': False
        }
        
        # TODO: Agregar inferencia aquí
        # detections = self.inference_system.detect(frame)
        # result['detections'] = detections
        
        # TODO: Determinar si se debe generar alerta
        # if self.should_generate_alert(detections):
        #     result['should_alert'] = True
        #     self.alert_emitter.emit_alert(uri, detections, frame)
        
        # TODO: Agregar frame a buffer para clips
        # self.clip_constructor.add_frame(uri, frame, detections)
        
        return result
    
    def main_loop(self):
        """Loop principal de procesamiento."""
        print("🎬 Iniciando procesamiento...")
        print("   (Presiona Ctrl+C para detener)\n")
        
        self.running = True
        self.stats['start_time'] = datetime.now()
        
        frame_count = 0
        last_stats_time = time.time()
        
        try:
            while self.running:
                # Obtener todas las cámaras activas
                active_cameras = self.rtsp_manager.get_all_active_connections()
                
                if not active_cameras:
                    print("⚠️  Sin cámaras activas, esperando...")
                    logger.warning("No active cameras available")
                    time.sleep(2)
                    continue
                
                # Procesar cada cámara
                for uri, cap in active_cameras.items():
                    try:
                        # Leer frame
                        ret, frame = cap.read()
                        
                        if ret:
                            # ✅ CRÍTICO: Actualizar heartbeat
                            self.rtsp_manager.update_frame_heartbeat(uri)
                            
                            # Procesar frame
                            result = self.process_frame(uri, frame)
                            
                            # Actualizar estadísticas
                            self.stats['frames_processed'] += 1
                            if result.get('should_alert'):
                                self.stats['alerts_sent'] += 1
                            
                            frame_count += 1
                        
                        else:
                            logger.warning(f"Frame read failed: {uri}")
                    
                    except Exception as e:
                        logger.error(f"Frame processing error [{uri}]: {e}")
                        continue
                
                # Mostrar estadísticas cada 30 segundos
                current_time = time.time()
                if current_time - last_stats_time >= 30:
                    self.show_statistics()
                    last_stats_time = current_time
                
                # Control de FPS (opcional, ajustar según necesidad)
                # time.sleep(0.033)  # ~30 FPS
                # time.sleep(0.1)    # ~10 FPS
                # Sin sleep = máxima velocidad
        
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Interrupción detectada, cerrando...\n")
        
        except Exception as e:
            print(f"\n❌ Error fatal: {e}\n")
            logger.error(f"Fatal error in main loop: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.running = False
    
    def show_statistics(self):
        """Mostrar estadísticas del sistema."""
        if self.stats['start_time']:
            elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
            fps = self.stats['frames_processed'] / elapsed if elapsed > 0 else 0
        else:
            elapsed = 0
            fps = 0
        
        # Estado de conexiones
        status = self.rtsp_manager.get_status_summary()
        
        print(f"\n{'='*70}")
        print("📊 ESTADÍSTICAS DEL SISTEMA")
        print(f"{'='*70}")
        print(f"⏱️  Tiempo activo: {elapsed:.1f}s")
        print(f"📹 Frames procesados: {self.stats['frames_processed']}")
        print(f"⚡ FPS promedio: {fps:.2f}")
        print(f"🎯 Detecciones: {self.stats['detections']}")
        print(f"📢 Alertas enviadas: {self.stats['alerts_sent']}")
        print(f"\n🎥 Cámaras:")
        print(f"   ✅ Conectadas: {status['connected']}")
        print(f"   ⚠️  Desconectadas: {status['disconnected']}")
        print(f"   🚫 Fallidas: {status['failed']}")
        print(f"{'='*70}\n")
    
    def shutdown(self):
        """Cerrar el sistema de forma ordenada."""
        print(f"\n🛑 Cerrando sistema...\n")
        
        self.running = False
        
        # Mostrar estadísticas finales
        self.show_statistics()
        
        # Cerrar conexiones RTSP
        self.rtsp_manager.close_all_connections()
        
        # TODO: Cerrar otros componentes
        # if self.inference_system:
        #     self.inference_system.cleanup()
        # if self.alert_emitter:
        #     self.alert_emitter.close()
        # if self.clip_constructor:
        #     self.clip_constructor.finalize()
        
        print("✅ Sistema cerrado correctamente\n")
        logger.info("System shutdown complete")


def load_config() -> dict:
    """
    Cargar configuración del sistema.
    
    Returns:
        Diccionario con configuración
    """
    # TODO: Cargar desde archivo config.json o similar
    config = {
        # Conexiones RTSP
        'rtsp_uris_path': 'rtsp-uris.json',
        'check_interval': 30,        # Verificar conexiones cada 30s
        'max_retries': 5,            # Máximo 5 reintentos
        'connection_timeout': 5,     # Timeout de conexión 5s
        'read_timeout': 10,          # Timeout de lectura 10s
        'backoff_max': 60,           # Backoff máximo 60s
        
        # Modelo de inferencia (TODO)
        'model_path': 'devkol-model/',
        'confidence_threshold': 0.5,
        'nms_threshold': 0.4,
        
        # Alertas (TODO)
        'alert_cooldown': 60,        # Segundos entre alertas de la misma cámara
        'alert_methods': ['log'],    # ['email', 'webhook', 'log']
        
        # Clips (TODO)
        'clip_duration': 10,         # Segundos de duración del clip
        'clip_buffer_before': 3,     # Segundos antes de la detección
        'clip_buffer_after': 7,      # Segundos después de la detección
        'clips_output_dir': 'clips/',
        
        # Performance
        'target_fps': None,          # None = máxima velocidad, o especificar FPS
        'resize_frame': None,        # None o (width, height) para resize
    }
    
    return config


def main():
    """Función principal."""
    print("\n" + "="*70)
    print("🛡️  SISTEMA DE DETECCIÓN DE SHOPLIFTING CON IA")
    print("="*70 + "\n")
    
    # Cargar configuración
    config = load_config()
    
    # Crear sistema
    system = ShopliftingDetectionSystem(config)
    
    try:
        # Inicializar sistema
        system.initialize()
        
        # Ejecutar loop principal
        system.main_loop()
    
    except Exception as e:
        print(f"❌ Error fatal: {e}\n")
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cerrar sistema
        system.shutdown()


if __name__ == "__main__":
    main()
