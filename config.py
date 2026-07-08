"""アプリケーション全体で共有する設定と定数を管理するモジュール。

環境変数(.env)から読み込む値と、コード全体で使うマジックナンバーを
一箇所に集約することで保守性を高める。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

# .env を一度だけ読み込む。
load_dotenv()

# --- API / モデル関連の定数 ---------------------------------------------------
DEFAULT_GEMINI_MODEL: str = "gemini-1.5-flash"
DEFAULT_DATABASE_URL: str = "sqlite:///x_search.db"
DEFAULT_LOG_LEVEL: str = "INFO"

X_API_BASE_URL: str = "https://api.x.com/2"
X_API_TIMEOUT_SECONDS: int = 30
X_SEARCH_MAX_RESULTS_LIMIT: int = 100
X_SEARCH_MAX_RESULTS_MIN: int = 10
X_USER_TWEETS_COUNT: int = 20
X_USER_TWEETS_MAX: int = 100

# --- 取得件数のデフォルト値 ---------------------------------------------------
DEFAULT_MAX_RESULTS: int = 20

# --- キャッシュ関連 -----------------------------------------------------------
ANALYSIS_CACHE_TTL_DAYS: int = 7

# --- 推薦スコア関連 -----------------------------------------------------------
SIMILARITY_SCORE_MIN: float = 0.0
SIMILARITY_SCORE_MAX: float = 100.0

# Gemini が返す特徴量スコアの想定レンジ (0-100)。
FEATURE_SCORE_MIN: float = 0.0
FEATURE_SCORE_MAX: float = 100.0


@dataclass(frozen=True)
class Settings:
    """環境変数から解決したアプリケーション設定を保持する不変オブジェクト。"""

    x_bearer_token: str
    gemini_api_key: str
    gemini_model: str = DEFAULT_GEMINI_MODEL
    database_url: str = DEFAULT_DATABASE_URL
    log_level: str = DEFAULT_LOG_LEVEL

    # API キーが揃っているかどうか。UI 側の警告表示に利用する。
    missing_keys: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_x_configured(self) -> bool:
        """X API を利用できる状態かどうかを返す。"""
        return bool(self.x_bearer_token)

    @property
    def is_gemini_configured(self) -> bool:
        """Gemini API を利用できる状態かどうかを返す。"""
        return bool(self.gemini_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """環境変数から `Settings` を構築して返す(結果はキャッシュされる)。

    Returns:
        Settings: 解決済みのアプリケーション設定。
    """
    x_bearer_token = os.getenv("X_BEARER_TOKEN", "").strip()
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

    missing: list[str] = []
    if not x_bearer_token:
        missing.append("X_BEARER_TOKEN")
    if not gemini_api_key:
        missing.append("GEMINI_API_KEY")

    return Settings(
        x_bearer_token=x_bearer_token,
        gemini_api_key=gemini_api_key,
        gemini_model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip(),
        database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip(),
        log_level=os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper(),
        missing_keys=tuple(missing),
    )
