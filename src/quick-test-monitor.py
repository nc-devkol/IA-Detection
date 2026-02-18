"""
Script minimalista para probar el monitor RTSP rápidamente.
Uso: python quick-test-monitor.py
"""

import sys
import os
import time
import importlib

sys.path.insert(0, os.path.dirname(__file__))
rtsp_connection = importlib.import_module('rtsp-connection')
RTSPConnectionManager = rtsp_connection.RTSPConnectionManager

# Configurar
json_path = os.path.join(os.path.dirname(__file__), "..", "rtsp-uris.json")

print("\n🚀 Iniciando prueba rápida del monitor RTSP\n")

# Crear gestor
manager = RTSPConnectionManager(
    json_path=json_path,
    check_interval=15,
    max_retries=3
)

# Inicializar
print("🔌 Conectando a cámaras...")
manager.initialize_all_connections()

# Mostrar estado
status = manager.get_status_summary()
print(f"\n✅ Conectadas: {status['connected']}/{status['total']}\n")

# Iniciar monitor
print("👁️  Monitor iniciado (Ctrl+C para salir)\n")
manager.start_monitoring()

try:
    # Loop principal: leer frames y actualizar heartbeat
    while True:
        active = manager.get_all_active_connections()
        
        for uri, cap in active.items():
            ret, frame = cap.read()
            if ret:
                # ¡IMPORTANTE! Actualizar heartbeat
                manager.update_frame_heartbeat(uri)
                print(f"📹 {uri}: {frame.shape}")
        
        time.sleep(1)  # Leer cada segundo

except KeyboardInterrupt:
    print("\n\n🛑 Deteniendo...\n")

finally:
    manager.close_all_connections()
    print("✅ Cerrado\n")
