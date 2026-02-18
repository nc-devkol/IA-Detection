"""
Ejemplo de uso del sistema de gestión de conexiones RTSP con reconexión automática.

Este script demuestra cómo:
1. Inicializar el gestor de conexiones
2. Conectar a múltiples cámaras RTSP
3. Monitorear y reconectar automáticamente
4. Procesar frames de las cámaras activas
"""

import cv2
import time
import sys
import os

# Agregar el directorio src al path para imports
sys.path.insert(0, os.path.dirname(__file__))

# Importar usando el nombre del archivo con guiones
import importlib
rtsp_connection = importlib.import_module('rtsp-connection')
RTSPConnectionManager = rtsp_connection.RTSPConnectionManager


def main():
    # ========== CONFIGURACIÓN ==========
    # Ruta al archivo JSON con las URIs RTSP
    JSON_PATH = "../rtsp-uris.json"
    
    # Intervalo de verificación en segundos (cada cuánto verifica las conexiones)
    CHECK_INTERVAL = 30  # 30 segundos
    
    # Número máximo de reintentos antes de marcar una cámara como fallida
    MAX_RETRIES = 3
    
    
    # ========== INICIALIZACIÓN ==========
    print("🚀 Iniciando sistema de gestión RTSP\n")
    
    # Crear el gestor de conexiones
    manager = RTSPConnectionManager(
        json_path=JSON_PATH,
        check_interval=CHECK_INTERVAL,
        max_retries=MAX_RETRIES
    )
    
    # Inicializar todas las conexiones
    manager.initialize_all_connections()
    
    # Iniciar el sistema de monitoreo automático
    manager.start_monitoring()
    
    
    # ========== PROCESAMIENTO DE FRAMES ==========
    print("\n📹 Comenzando procesamiento de frames...")
    print("Presiona Ctrl+C para detener\n")
    
    try:
        frame_count = 0
        
        while True:
            # Obtener todas las conexiones activas
            active_connections = manager.get_all_active_connections()
            
            if not active_connections:
                print("⚠️ No hay cámaras activas. Esperando reconexión...")
                time.sleep(2)
                continue
            
            # Procesar cada cámara activa
            for uri, cap in active_connections.items():
                ret, frame = cap.read()
                
                if ret:
                    # Aquí puedes procesar el frame (detección, inferencia, etc.)
                    # Por ahora solo mostramos info
                    height, width = frame.shape[:2]
                    
                    # Opcional: mostrar el frame
                    # cv2.imshow(f"Camera: {uri}", frame)
                    
                    if frame_count % 30 == 0:  # Mostrar cada 30 frames
                        print(f"📸 {uri}: Frame {width}x{height}")
                else:
                    print(f"⚠️ No se pudo leer frame de {uri}")
            
            frame_count += 1
            
            # Pequeña pausa para no saturar la CPU
            time.sleep(0.033)  # ~30 FPS
            
            # Cada 100 frames, mostrar resumen de estado
            if frame_count % 100 == 0:
                status = manager.get_status_summary()
                print(f"\n📊 Estado del sistema:")
                print(f"   Total: {status['total']}")
                print(f"   Conectadas: ✅ {status['connected']}")
                print(f"   Desconectadas: ⚠️ {status['disconnected']}")
                print(f"   Fallidas: 🚫 {status['failed']}\n")
            
            # Manejo de teclas para OpenCV (si usas cv2.imshow)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupción detectada por el usuario")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    finally:
        # ========== LIMPIEZA ==========
        print("\n🧹 Cerrando sistema...")
        manager.close_all_connections()
        cv2.destroyAllWindows()
        print("✅ Sistema cerrado correctamente\n")


def example_single_camera():
    """Ejemplo simplificado para trabajar con una sola cámara."""
    
    manager = RTSPConnectionManager(
        json_path="../rtsp-uris.json",
        check_interval=20,
        max_retries=5
    )
    
    # Inicializar conexiones
    manager.initialize_all_connections()
    
    # Iniciar monitoreo
    manager.start_monitoring()
    
    # Obtener la primera URI disponible
    status = manager.get_status_summary()
    if status['connected'] > 0:
        first_uri = list(manager.get_all_active_connections().keys())[0]
        print(f"🎥 Trabajando con: {first_uri}")
        
        # Procesar frames
        for i in range(100):
            cap = manager.get_connection(first_uri)
            if cap:
                ret, frame = cap.read()
                if ret:
                    print(f"Frame {i}: {frame.shape}")
            time.sleep(0.1)
    
    # Cerrar
    manager.close_all_connections()


def example_check_specific_camera():
    """Ejemplo de cómo verificar una cámara específica."""
    
    manager = RTSPConnectionManager(
        json_path="../rtsp-uris.json",
        check_interval=30
    )
    
    manager.initialize_all_connections()
    manager.start_monitoring()
    
    # URI específica a monitorear
    target_uri = "rtsp://example.com/stream1"
    
    try:
        for _ in range(10):
            cap = manager.get_connection(target_uri)
            
            if cap is not None:
                ret, frame = cap.read()
                if ret:
                    print(f"✅ {target_uri} está funcionando")
                else:
                    print(f"⚠️ {target_uri} no puede leer frames")
            else:
                print(f"❌ {target_uri} no está conectado")
            
            time.sleep(5)
    
    finally:
        manager.close_all_connections()


if __name__ == "__main__":
    # Ejecutar el ejemplo principal
    main()
    
    # Descomentar para ejecutar otros ejemplos:
    # example_single_camera()
    # example_check_specific_camera()
