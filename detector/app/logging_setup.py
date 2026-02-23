import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(log_dir: str, name: str = "detector") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_path = os.path.join(log_dir, "detector.log")
    fh = RotatingFileHandler(file_path, maxBytes=5_000_000, backupCount=5)
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)

    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger