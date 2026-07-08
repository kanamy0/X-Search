"""特徴量ベクトル間の一致率(類似度)を計算する推薦サービス。

コサイン類似度をベースに 0〜100% の一致率へ変換する。
将来的なベクトル検索への差し替えを見据え、計算ロジックを独立させる。
"""

from __future__ import annotations

import math

from config import SIMILARITY_SCORE_MAX, SIMILARITY_SCORE_MIN
from services.schemas import FeatureProfile
from utils.logger import get_logger

logger = get_logger(__name__)


class RecommendService:
    """特徴量プロファイルの類似度計算と共通趣味抽出を担うサービス。"""

    def match_rate(
        self, query: FeatureProfile, candidate: FeatureProfile
    ) -> float:
        """入力プロファイルと候補プロファイルの一致率(0-100)を計算する。

        Args:
            query: ユーザー入力から生成した理想プロファイル。
            candidate: 候補ユーザーのプロファイル。

        Returns:
            float: 一致率(0.0〜100.0)。
        """
        similarity = self._cosine_similarity(
            query.feature_dict(), candidate.feature_dict()
        )
        rate = similarity * SIMILARITY_SCORE_MAX
        return self._clamp(rate)

    def common_interests(
        self, query: FeatureProfile, candidate: FeatureProfile
    ) -> list[str]:
        """入力と候補の双方で高スコアな共通趣味ラベルを抽出する。

        Args:
            query: ユーザー入力から生成した理想プロファイル。
            candidate: 候補ユーザーのプロファイル。

        Returns:
            list[str]: 共通する趣味・関心ラベルのリスト。
        """
        query_features = query.feature_dict()
        candidate_features = candidate.feature_dict()
        common = [
            label.split(".", 1)[-1]
            for label in query_features
            if label in candidate_features
        ]
        # 重複を避けつつ順序を保持する。
        return list(dict.fromkeys(common))

    @staticmethod
    def _cosine_similarity(
        vec_a: dict[str, float], vec_b: dict[str, float]
    ) -> float:
        """疎ベクトル(辞書)同士のコサイン類似度を計算する。

        Returns:
            float: 0.0〜1.0 の類似度。片方が空なら 0.0。
        """
        if not vec_a or not vec_b:
            return 0.0
        shared_keys = set(vec_a) & set(vec_b)
        dot = sum(vec_a[key] * vec_b[key] for key in shared_keys)
        norm_a = math.sqrt(sum(value * value for value in vec_a.values()))
        norm_b = math.sqrt(sum(value * value for value in vec_b.values()))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _clamp(value: float) -> float:
        """一致率を有効範囲へ丸める。"""
        return max(SIMILARITY_SCORE_MIN, min(value, SIMILARITY_SCORE_MAX))
