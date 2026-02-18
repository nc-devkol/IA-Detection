import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional
from datetime import datetime


class LogGenerator:
    """
    Logger reutilizable para aplicaciones.
    - Soporta archivo con rotación
    - Soporta salida en consola
    - Thread-safe
    - Reutilizable por módulos
    - Logs con fecha en el nombre
    """
    
    _initialized = False  # Flag para evitar múltiples configuraciones

    def __init__(
        self,
        log_dir: str = "logs",
        log_file: str = "application.log",
        level: int = logging.INFO,
        max_bytes: int = 5 * 1024 * 1024,  # 5MB
        backup_count: int = 5,
        console: bool = True,
        include_date: bool = True
    ):
        """
        Args:
            log_dir: Carpeta donde se guardan los logs (relativa o absoluta)
            log_file: Nombre del archivo principal (ej: "app.log")
            level: Nivel mínimo de log
            max_bytes: Tamaño máximo antes de rotar
            backup_count: Número de archivos de respaldo
            console: Si también imprime en consola
            include_date: Si True, agrega fecha al nombre (ej: "app_2026-02-18.log")
        """

        # Convertir a ruta absoluta si es relativa
        if not os.path.isabs(log_dir):
            # Si es relativa, construir desde el directorio raíz del proyecto
            # Asumiendo que src/ está en la raíz del proyecto
            project_root = Path(__file__).parent.parent
            self.log_dir = str(project_root / log_dir)
        else:
            self.log_dir = log_dir
        
        # Agregar fecha al nombre del archivo si se solicita
        if include_date:
            date_str = datetime.now().strftime('%Y-%m-%d')
            # Separar nombre y extensión
            name_parts = log_file.rsplit('.', 1)
            if len(name_parts) == 2:
                self.log_file = f"{name_parts[0]}_{date_str}.{name_parts[1]}"
            else:
                self.log_file = f"{log_file}_{date_str}"
        else:
            self.log_file = log_file
        
        self.level = level
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.console = console

        # Crear directorio si no existe
        os.makedirs(self.log_dir, exist_ok=True)

        # Configurar logger
        self._configure_root_logger()

    def _configure_root_logger(self):
        """Configura el logger raíz solo una vez."""
        
        # Si ya está inicializado, solo agregar handlers adicionales si es necesario
        if LogGenerator._initialized:
            return

        logger = logging.getLogger()
        logger.setLevel(self.level)

        # Limpiar handlers existentes para evitar duplicación
        logger.handlers.clear()

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(threadName)-12s | %(name)-20s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Handler para archivo con rotación
        file_path = os.path.join(self.log_dir, self.log_file)
        try:
            file_handler = RotatingFileHandler(
                file_path,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(self.level)
            logger.addHandler(file_handler)
            
            # Confirmación en consola (con emoji para usuario)
            print(f"📄 Log file: {file_path}")
            
        except Exception as e:
            print(f"⚠️  Error creating log file {file_path}: {e}")

        # Handler consola
        if self.console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(self.level)
            logger.addHandler(console_handler)
        
        LogGenerator._initialized = True

    @staticmethod
    def get_logger(name: Optional[str] = None) -> logging.Logger:
        """
        Devuelve un logger por módulo.

        Uso recomendado:
        logger = LogGenerator.get_logger(__name__)
        """
        return logging.getLogger(name)
    
    @staticmethod
    def reset():
        """Resetear el sistema de logging (útil para testing)."""
        logging.getLogger().handlers.clear()
        LogGenerator._initialized = False
