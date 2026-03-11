"""logger.py — centralized logging for all scraper modules"""

import logging
import sys
from pathlib import Path
from datetime import datetime


def get_logger(name: str) -> logging.Logger:
    """Get a named logger with console + file output."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler — INFO and above
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(console)

    # File handler — DEBUG and above
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(
        log_dir / f"scraper_{datetime.now():%Y%m%d}.log",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    ))
    logger.addHandler(file_handler)

    return logger
