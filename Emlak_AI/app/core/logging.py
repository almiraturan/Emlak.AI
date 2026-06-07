"""Structured logging configuration for EmlakAI."""

import logging
import json
from datetime import datetime
from typing import Any
from pythonjsonlogger import jsonlogger


class StructuredLogFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging."""

    def add_fields(self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        
        # İsim ve seviye ekle
        log_record["logger"] = record.name
        log_record["level"] = record.levelname
        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        # Hata varsa stack trace ekle
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging."""
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # JSON handler (stdout'a)
    json_handler = logging.StreamHandler()
    json_formatter = StructuredLogFormatter()
    json_handler.setFormatter(json_formatter)
    
    # Var olan handlers'ı temizle
    root_logger.handlers.clear()
    root_logger.addHandler(json_handler)
    
    # uvicorn loggers'ı da yapılandır
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.addHandler(json_handler)
        logger.setLevel(getattr(logging, level.upper()))


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger."""
    return logging.getLogger(name)
