"""サービス層で共有する pydantic スキーマ定義。

Gemini が返す特徴量 JSON の構造を型として表現し、
解析失敗時の検出とベクトル化を容易にする。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from config import GENDER_UNKNOWN, GENDER_VALUES

# メトリクス名 -> 日本語ラベル(フィルタ説明の生成に利用)。
_METRIC_LABELS: dict[str, str] = {
    "followers": "フォロワー数",
    "following": "フォロー数",
    "posts": "投稿数",
}


class MetricRange(BaseModel):
    """1 つのメトリクスに対する下限・上限の範囲条件。"""

    minimum: int | None = None
    maximum: int | None = None

    @property
    def is_empty(self) -> bool:
        """下限・上限のいずれも指定されていなければ True。"""
        return self.minimum is None and self.maximum is None

    def contains(self, value: int) -> bool:
        """値が範囲内かどうかを判定する。"""
        if self.minimum is not None and value < self.minimum:
            return False
        if self.maximum is not None and value > self.maximum:
            return False
        return True


class CandidateFilter(BaseModel):
    """候補アカウントを数値メトリクスで絞り込むためのフィルタ。

    自然文の指定(例: 「フォロワー1000人以上」「投稿が少ない人」)を
    解釈した結果を、フォロワー数・フォロー数・投稿数の範囲として保持する。
    """

    followers: MetricRange = Field(default_factory=MetricRange)
    following: MetricRange = Field(default_factory=MetricRange)
    posts: MetricRange = Field(default_factory=MetricRange)

    def _ranges(self) -> list[tuple[str, MetricRange]]:
        """(メトリクス名, 範囲) の並びを固定順で返す内部ヘルパー。"""
        return [
            ("followers", self.followers),
            ("following", self.following),
            ("posts", self.posts),
        ]

    @property
    def is_empty(self) -> bool:
        """有効な条件が 1 つも無ければ True。"""
        return all(rng.is_empty for _, rng in self._ranges())

    def matches(self, followers: int, following: int, posts: int) -> bool:
        """与えられたメトリクスがフィルタ条件をすべて満たすか判定する。

        Args:
            followers: フォロワー数。
            following: フォロー数。
            posts: 投稿数(累計)。

        Returns:
            bool: すべての条件を満たせば True。
        """
        return (
            self.followers.contains(followers)
            and self.following.contains(following)
            and self.posts.contains(posts)
        )

    def describe(self) -> str:
        """人が読める形式で有効な条件を要約する。"""
        parts: list[str] = []
        for metric, rng in self._ranges():
            label = _METRIC_LABELS[metric]
            if rng.minimum is not None and rng.maximum is not None:
                parts.append(f"{label} {rng.minimum:,}〜{rng.maximum:,}")
            elif rng.minimum is not None:
                parts.append(f"{label} {rng.minimum:,} 以上")
            elif rng.maximum is not None:
                parts.append(f"{label} {rng.maximum:,} 以下")
        return " / ".join(parts)


class FeatureProfile(BaseModel):
    """Gemini が返す趣味・関心の特徴量プロファイル。

    各カテゴリはラベルからスコア(0-100)への辞書。
    未知のラベルにも対応できるよう任意のキーを許容する。
    """

    games: dict[str, float] = Field(default_factory=dict)
    contents: dict[str, float] = Field(default_factory=dict)
    communication: dict[str, float] = Field(default_factory=dict)
    activity: dict[str, float] = Field(default_factory=dict)
    summary: str = ""

    # 公開情報から推定した性別("male"/"female"/"unknown")と確信度(0-100)。
    # 厳密な性別ではなく、あくまで文体・話題からの推定であることに注意。
    gender: str = GENDER_UNKNOWN
    gender_confidence: float = 0.0

    @field_validator("gender", mode="before")
    @classmethod
    def _normalize_gender(cls, value: object) -> str:
        """想定外の値は「不明」に正規化する。"""
        if isinstance(value, str) and value.lower() in GENDER_VALUES:
            return value.lower()
        return GENDER_UNKNOWN

    def feature_dict(self) -> dict[str, float]:
        """カテゴリを平坦化した「ラベル -> スコア」の辞書を返す。

        コサイン類似度計算のためのベクトル生成に用いる。名前衝突を防ぐため
        カテゴリ名を接頭辞として付与する。

        Returns:
            dict[str, float]: 平坦化された特徴量辞書。
        """
        flat: dict[str, float] = {}
        for category in ("games", "contents", "communication", "activity"):
            values: dict[str, float] = getattr(self, category)
            for label, score in values.items():
                flat[f"{category}.{label}"] = float(score)
        return flat
