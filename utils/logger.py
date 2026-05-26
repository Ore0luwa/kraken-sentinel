import logging, sys

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(f"sentinel.{name}")
    if not logger.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(h)
    logger.setLevel(level)
    return logger
