import datetime
import json
import logging
import os


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
        payload = {
            "timestamp": timestamp.replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "event_name", record.getMessage()),
        }

        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("nyx")
    if logger.handlers:
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.getenv("NYX_LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"nyx.{name}")


def log_event(logger: logging.Logger, level: int, event: str, **fields) -> None:
    logger.log(level, event, extra={"event_name": event, "fields": fields})
