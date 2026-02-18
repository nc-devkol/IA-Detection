# Sistema de Detección de Shoplifting con IA

## 🚀 Inicio Rápido

### Ejecutar el sistema completo:

```powershell
python main.py
```

## 📁 Estructura del Proyecto

```
IA-Detection-Shoplifting/
├── main.py                      # ⭐ Punto de entrada principal
├── config.json                  # Configuración del sistema
├── rtsp-uris.json              # Lista de cámaras RTSP
│
├── src/                        # Módulos del sistema
│   ├── rtsp-connection.py     # ✅ Gestor de conexiones RTSP
│   ├── inference-system.py    # 🧠 Sistema de inferencia (TODO)
│   ├── alert-emitter.py       # 📢 Emisor de alertas (TODO)
│   ├── clip-constructor.py    # 🎬 Constructor de clips (TODO)
│   ├── logs-generator.py      # 📝 Sistema de logging
│   └── view-alerts.py         # 👁️  Visualizador de alertas
│
├── devkol-model/              # Modelo de detección
├── logs/                      # Logs del sistema
├── clips/                     # Clips de evidencia
└── documentation/             # Documentación

```

## 🔄 Flujo del Sistema

```
1. main.py
   ↓
2. Inicializar RTSPConnectionManager
   ↓
3. Conectar a todas las cámaras (rtsp-uris.json)
   ↓
4. Iniciar monitor de reconexión (background thread)
   ↓
5. Loop principal:
   │
   ├─→ Leer frames de cámaras activas
   ├─→ Actualizar heartbeat (mantener conexión viva)
   ├─→ Ejecutar inferencia (detección de shoplifting)  ← TODO
   ├─→ Generar alertas si hay detección                ← TODO
   └─→ Guardar clips de evidencia                      ← TODO
```

## ⚙️ Configuración

### Archivo `config.json`

```json
{
  "rtsp": {
    "check_interval": 30,        // Verificar conexiones cada 30s
    "max_retries": 5             // Reintentar 5 veces antes de marcar como fallida
  },
  "inference": {
    "confidence_threshold": 0.5  // Umbral de confianza para detecciones
  },
  "alerts": {
    "cooldown_seconds": 60       // No alertar la misma cámara por 60s
  }
}
```

### Archivo `rtsp-uris.json`

```json
{
  "URIS_LIST": [
    "rtsp://192.168.1.100:554/stream1",
    "rtsp://192.168.1.101:554/stream1"
  ]
}
```

## 📦 Componentes Implementados

### ✅ RTSPConnectionManager (`src/rtsp-connection.py`)

**Estado: COMPLETO**

Características:
- ✅ Conexión a múltiples cámaras RTSP
- ✅ Monitoreo continuo de salud (heartbeat)
- ✅ Reconexión automática con backoff exponencial
- ✅ Thread-safe con locks optimizados
- ✅ Timeouts configurables de FFmpeg
- ✅ Logging profesional con rotación

**Uso:**
```python
from rtsp_connection import RTSPConnectionManager

manager = RTSPConnectionManager('rtsp-uris.json')
manager.initialize_all_connections()
manager.start_monitoring()

# Leer frames
for uri, cap in manager.get_all_active_connections().items():
    ret, frame = cap.read()
    if ret:
        manager.update_frame_heartbeat(uri)  # ¡Importante!
        # Procesar frame...
```

### 🔜 InferenceSystem (`src/inference-system.py`)

**Estado: TODO**

Características planeadas:
- Cargar modelo desde `devkol-model/`
- Ejecutar inferencia en frames
- Detectar comportamientos de shoplifting
- Retornar detecciones con bounding boxes y confianza

**Interfaz propuesta:**
```python
class InferenceSystem:
    def __init__(self, model_path, confidence_threshold):
        pass
    
    def detect(self, frame):
        # Retornar lista de detecciones
        return [
            {
                'class': 'shoplifting',
                'confidence': 0.85,
                'bbox': [x1, y1, x2, y2]
            }
        ]
```

### 🔜 AlertEmitter (`src/alert-emitter.py`)

**Estado: TODO**

Características planeadas:
- Emisión de alertas por múltiples canales (email, webhook, log)
- Cooldown para evitar spam de alertas
- Queue de alertas para procesamiento asíncrono
- Inclusión de frame/clip de evidencia

**Interfaz propuesta:**
```python
class AlertEmitter:
    def emit_alert(self, uri, detections, frame):
        # Enviar alerta por canales configurados
        pass
```

### 🔜 ClipConstructor (`src/clip-constructor.py`)

**Estado: TODO**

Características planeadas:
- Buffer circular de frames por cámara
- Generación de clips de N segundos
- Incluir frames antes y después de la detección
- Guardar en formato configurable (MP4, AVI)

**Interfaz propuesta:**
```python
class ClipConstructor:
    def add_frame(self, uri, frame, timestamp):
        # Agregar frame al buffer
        pass
    
    def create_clip(self, uri, detection_time):
        # Crear y guardar clip
        return clip_path
```

## 🧪 Testing

### Probar solo conexiones RTSP:

```powershell
# Modo interactivo
cd src
python rtsp-connection.py

# Con parámetros
python rtsp-connection.py --interval 15 --retries 5
```

### Probar sistema completo (sin inferencia aún):

```powershell
python main.py
```

## 📊 Logs

Los logs se guardan en `logs/` con rotación automática:

- `logs/main.log` - Log principal del sistema
- `logs/rtsp-connections.log` - Log de conexiones RTSP

Formato:
```
2026-02-18 14:30:45 | INFO | MainThread | __main__ | Sistema inicializado
2026-02-18 14:30:45 | INFO | Thread-1 | rtsp-connection | Monitor iniciado
```

## 🎯 Próximos Pasos

1. **Implementar InferenceSystem** (`src/inference-system.py`)
   - Cargar modelo de `devkol-model/`
   - Ejecutar detección en frames
   
2. **Implementar AlertEmitter** (`src/alert-emitter.py`)
   - Sistema de alertas con cooldown
   - Múltiples canales (email, webhook)
   
3. **Implementar ClipConstructor** (`src/clip-constructor.py`)
   - Buffer circular de frames
   - Generación de clips de evidencia
   
4. **Integrar todo en `main.py`**
   - Descomentar las líneas TODO
   - Conectar el flujo completo

## 🐛 Troubleshooting

### No se conectan las cámaras
- Verificar URIs en `rtsp-uris.json`
- Revisar logs en `logs/rtsp-connections.log`
- Asegurarse que las cámaras son accesibles en la red

### Heartbeat timeout
- Asegurarse de llamar `update_frame_heartbeat(uri)` después de cada frame exitoso
- Ajustar `check_interval` en config si la red es lenta

### Alto uso de CPU
- Reducir FPS objetivo en config
- Reducir resolución de frames con `resize_frames`
- Reducir número de cámaras simultáneas

## 📚 Documentación Adicional

- [Arquitectura del Sistema](documentation/Architecture.md)
- [Sistema de Conexiones RTSP](documentation/RTSP-Connection-System.md)
- [Configuración de Red](documentation/Ethernet%20Config%20Instructions.md)

---

**Estado actual:** ✅ Conexiones RTSP completas | 🔜 Inferencia, alertas y clips pendientes
