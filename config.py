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
# 軽量・低コストなモデルを既定にしてトークン消費とレイテンシを抑える。
DEFAULT_GEMINI_MODEL: str = "gemini-2.5-flash-lite"
DEFAULT_DATABASE_URL: str = "sqlite:///x_search.db"
DEFAULT_LOG_LEVEL: str = "INFO"

X_API_BASE_URL: str = "https://api.x.com/2"
X_API_TIMEOUT_SECONDS: int = 30
X_SEARCH_MAX_RESULTS_LIMIT: int = 100
X_SEARCH_MAX_RESULTS_MIN: int = 10
X_USER_TWEETS_COUNT: int = 20
X_USER_TWEETS_MAX: int = 100

# Gemini へ渡す投稿の上限(トークン節約のため件数・文字数をトリムする)。
GEMINI_MAX_POSTS_FOR_ANALYSIS: int = 20
GEMINI_MAX_POST_CHARS: int = 280

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

# --- 自然文フィルタ関連 -------------------------------------------------------
# 「フォロワー1000人以上」「投稿が多い人」等の自然文条件を、候補の
# フォロワー数・フォロー数・投稿数へのしきい値としてルールベースで解釈する。

# 対象メトリクスごとの検出キーワード(前方から順にマッチを試みるため、
# 「フォロワー」を「フォロー」より先に並べる)。
FILTER_METRIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "followers": ("フォロワー", "follower", "ファン"),
    "following": ("フォロー", "following", "フォロー中"),
    "posts": ("投稿", "ツイート", "ポスト", "tweet", "post"),
}

# 下限(min)を表す比較表現。
FILTER_MIN_KEYWORDS: tuple[str, ...] = (
    "以上",
    "超",
    "より多い",
    "より上",
    "多い",
    "最低",
    "over",
    "min",
)
# 上限(max)を表す比較表現。
FILTER_MAX_KEYWORDS: tuple[str, ...] = (
    "以下",
    "未満",
    "より少ない",
    "より下",
    "少ない",
    "まで",
    "under",
    "max",
)
# 数値に付く日本語の桁表現(倍率)。
FILTER_NUMBER_UNITS: dict[str, int] = {"万": 10_000, "千": 1_000}
# 範囲指定(「1000〜5000」等)の区切り。
FILTER_RANGE_SEPARATORS: tuple[str, ...] = ("〜", "~", "から", "-")

# 数値を伴わない定性表現(「多い」「少ない」)に割り当てるしきい値。
FILTER_QUALITATIVE_THRESHOLDS: dict[str, int] = {
    "followers": 1_000,
    "following": 1_000,
    "posts": 1_000,
}

# --- 性別推定関連 -------------------------------------------------------------
# 性別は厳密には不明であるため、Gemini が公開プロフィール・投稿の文体や
# 話題から推定した値(確信度付き)を保持する。断定できない場合は「不明」。
GENDER_MALE: str = "male"
GENDER_FEMALE: str = "female"
GENDER_UNKNOWN: str = "unknown"
GENDER_VALUES: tuple[str, ...] = (GENDER_MALE, GENDER_FEMALE, GENDER_UNKNOWN)

# 内部値 -> 日本語ラベル(UI 表示に利用)。
GENDER_LABELS: dict[str, str] = {
    GENDER_MALE: "男性",
    GENDER_FEMALE: "女性",
    GENDER_UNKNOWN: "不明",
}

# UI の性別セレクトボックス(表示ラベル -> 内部値、None は絞り込みなし)。
GENDER_FILTER_CHOICES: dict[str, str | None] = {
    "指定なし": None,
    "男性": GENDER_MALE,
    "女性": GENDER_FEMALE,
}


def gender_label(value: str) -> str:
    """性別の内部値を日本語ラベルへ変換する(未知の値は「不明」)。"""
    return GENDER_LABELS.get(value, GENDER_LABELS[GENDER_UNKNOWN])


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
