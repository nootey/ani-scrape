import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from pythonjsonlogger import jsonlogger


class AppLogger:
    def __init__(
        self,
        name: str = __name__,
        log_dir: str = "logs",
        level: int = logging.INFO,
    ):
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.propagate = False  # avoid duplicate logs

        if not self.logger.handlers:
            log_file = Path(log_dir) / "app.log"

            # --- File handler (JSON format)
            file_handler = TimedRotatingFileHandler(
                filename=log_file,
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8",
                utc=False,
            )

            file_handler.suffix = "%Y-%m-%d"
            file_formatter = jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

            # --- Console handler (simple format)
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                "[%(levelname)s] %(asctime)s - %(message)s"
            )
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

    def get_logger(self):
        return self.logger
