import faulthandler
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "offline_translator"
_fault_file = None


def error_log_path() -> Path:
    """Путь к файлу лога ошибок приложения."""
    from app_settings import data_root

    return data_root() / "error.log"


def crash_log_path() -> Path:
    """Путь к дампу нативных падений (segfault / Access Violation)."""
    from app_settings import data_root

    return data_root() / "crash.log"


def get_logger() -> logging.Logger:
    """Общий логгер приложения."""
    return logging.getLogger(_LOGGER_NAME)


def setup_logging() -> Path:
    """Включает запись ошибок в файл и перехват необработанных исключений."""
    global _fault_file
    path = error_log_path()
    logger = get_logger()
    if logger.handlers:
        return path

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = RotatingFileHandler(
        path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(threadName)s %(message)s"
        )
    )
    logger.addHandler(handler)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(stderr_handler)

    sys.excepthook = _handle_uncaught
    threading.excepthook = _handle_thread_uncaught
    _enable_faulthandler()
    logger.info("Логирование включено: %s", path)
    flush_logs()
    return path


def flush_logs() -> None:
    """Сбрасывает буфер лога на диск — нужно перед рискованным кодом."""
    logger = get_logger()
    for handler in logger.handlers:
        try:
            handler.flush()
        except Exception:
            pass
    if _fault_file is not None:
        try:
            _fault_file.flush()
        except Exception:
            pass


def log_exception(message: str, error: BaseException | None = None) -> None:
    """Пишет ошибку со стеком в лог."""
    if error is None:
        get_logger().exception(message)
    else:
        get_logger().exception("%s: %s", message, error)


def _enable_faulthandler() -> None:
    """Пишет нативные краши в отдельный файл, если Python ещё может это сделать."""
    global _fault_file
    try:
        _fault_file = open(crash_log_path(), "a", encoding="utf-8")
        faulthandler.enable(file=_fault_file, all_threads=True)
    except Exception:
        _fault_file = None


def _handle_uncaught(exc_type, exc, traceback_obj) -> None:
    """Ловит необработанные исключения главного потока."""
    get_logger().critical(
        "Необработанная ошибка",
        exc_info=(exc_type, exc, traceback_obj),
    )
    flush_logs()
    sys.__excepthook__(exc_type, exc, traceback_obj)


def _handle_thread_uncaught(args) -> None:
    """Ловит необработанные исключения фоновых потоков."""
    thread_name = args.thread.name if args.thread is not None else "?"
    get_logger().critical(
        "Необработанная ошибка в потоке %s",
        thread_name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    flush_logs()
