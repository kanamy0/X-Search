"""アプリケーション共通のロガーを提供するモジュール。

`logging` を用い、原因追跡が容易なフォーマットで出力する。
"""

from __future__ import annotations

import logging
import sys

from config import get_settings

_LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# 同一名のロガーへ複数回ハンドラを追加しないための管理セット。
_configured_loggers: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    """名前付きロガーを取得する。

    Args:
        name: ロガー名(通常は `__name__`)。

    Returns:
        logging.Logger: 設定済みロガー。
    """
    logger = logging.getLogger(name)

    if name not in _configured_loggers:
        settings = get_settings()
        level = getattr(logging, settings.log_level, logging.INFO)
        logger.setLevel(level)

        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))
        logger.addHandler(handler)
        # ルートロガーへの伝播を止めて二重出力を防ぐ。
        logger.propagate = False

        _configured_loggers.add(name)

    return logger
