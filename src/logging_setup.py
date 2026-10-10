"""Metadata-only rotating logs."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("desk_guardian")
    logger.setLevel(logging.INFO)
    for existing in logger.handlers[:]:
        logger.removeHandler(existing)
        existing.close()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler = RotatingFileHandler(log_dir / "guardian.log", maxBytes=1_000_000, backupCount=2,
                                  encoding="utf-8")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    return logger
