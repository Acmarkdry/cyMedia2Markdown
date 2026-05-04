# -*- coding: UTF-8 -*-

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import env


def setup_logging(log_level: str = "INFO") -> None:
    """设置日志配置"""

    # 创建根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # 清除现有的处理器
    root_logger.handlers.clear()

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    # 设置标准格式化器
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # 添加处理器到根日志器
    root_logger.addHandler(console_handler)

    log_dir = Path(env.LOG_DIR)
    if not log_dir.is_absolute():
        log_dir = Path(__file__).resolve().parents[1] / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "backend.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 设置第三方库的日志级别
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


# 获取应用日志器
def get_logger(name: str) -> logging.Logger:
    """获取日志器实例"""
    return logging.getLogger(name)
