"""サービス層で共有する pydantic スキーマ定義。

Gemini が返す特徴量 JSON の構造を型として表現し、
解析失敗時の検出とベクトル化を容易にする。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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
