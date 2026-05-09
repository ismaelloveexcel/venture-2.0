"""
Structured logging for Venture OS.

Provides file-based logging with rotation, timestamps, and severity levels.
Useful for debugging Task Scheduler runs and production failures.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(
    log_dir: str = "logs",
    level: int = logging.INFO,
    name: str = "venture",
) -> logging.Logger:
    """
    Configure structured logging to file + console.
    
    Creates:
    - logs/venture-{date}.log — daily rollover, JSON-formatted
    - Console output for interactive runs
    
    Args:
        log_dir: Directory for log files (created if missing)
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        name: Logger name and file prefix
    
    Returns:
        Configured logger instance
    """
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Don't add handlers if already configured
    if logger.handlers:
        return logger
    
    # File handler with daily rotation
    log_file = log_path / f"{name}-{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=30,  # Keep 30 old files
    )
    file_handler.setLevel(level)
    
    # Console handler for interactive runs
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Formatter with timestamp, level, and message
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized to {log_file}")
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a module."""
    return logging.getLogger(name)
