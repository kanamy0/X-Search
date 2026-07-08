"""自然文の絞り込み条件を構造化フィルタへ変換するサービス。

「フォロワー1000人以上」「投稿が多い人」「フォロー 500 以下」といった
日本語の自然文を、フォロワー数・フォロー数・投稿数の範囲条件
(:class:`CandidateFilter`)へルールベースで解釈する。

外部 API を呼ばない決定論的な実装とすることで、Gemini のトークン消費を
増やさず、テストも容易にする。
"""

from __future__ import annotations

import re

from config import (
    FILTER_MAX_KEYWORDS,
    FILTER_METRIC_KEYWORDS,
    FILTER_MIN_KEYWORDS,
    FILTER_NUMBER_UNITS,
    FILTER_QUALITATIVE_THRESHOLDS,
    FILTER_RANGE_SEPARATORS,
)
from services.schemas import CandidateFilter, MetricRange
from utils.logger import get_logger

logger = get_logger(__name__)

# 節を区切る文字(句読点・接続表現)。
_CLAUSE_DELIMITERS = re.compile(r"[、,，。;；\n]|かつ|and|、")
# 数値(カンマ区切り・小数を許容)とそれに続く任意の桁単位(万・千)。
_NUMBER_PATTERN = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(万|千)?")


class FilterParser:
    """自然文の絞り込み条件を :class:`CandidateFilter` へ変換するパーサ。"""

    def parse(self, text: str) -> tuple[CandidateFilter, list[str]]:
        """自然文を解釈してフィルタと未解釈の節を返す。

        Args:
            text: 例「フォロワー1000人以上、投稿が多い人」。

        Returns:
            tuple[CandidateFilter, list[str]]:
                解釈したフィルタと、メトリクスを特定できなかった節のリスト。
        """
        candidate = CandidateFilter()
        unparsed: list[str] = []
        if not text or not text.strip():
            return candidate, unparsed

        for clause in self._split_clauses(text):
            metric = self._detect_metric(clause)
            if metric is None:
                unparsed.append(clause)
                continue
            self._apply_clause(candidate, metric, clause)

        logger.debug(
            "Parsed filter: %s (unparsed=%s)", candidate.describe(), unparsed
        )
        return candidate, unparsed

    @staticmethod
    def _split_clauses(text: str) -> list[str]:
        """入力文を節へ分割する。"""
        raw = _CLAUSE_DELIMITERS.split(text)
        return [c.strip() for c in raw if c and c.strip()]

    @staticmethod
    def _detect_metric(clause: str) -> str | None:
        """節がどのメトリクスに関する記述かを判定する。

        「フォロワー」を「フォロー」より優先して判定する必要があるため、
        まず followers を含むか確認してから他を評価する。
        """
        lowered = clause.lower()
        if any(kw.lower() in lowered for kw in FILTER_METRIC_KEYWORDS["followers"]):
            return "followers"
        for metric in ("following", "posts"):
            if any(kw.lower() in lowered for kw in FILTER_METRIC_KEYWORDS[metric]):
                return metric
        return None

    def _apply_clause(
        self, candidate: CandidateFilter, metric: str, clause: str
    ) -> None:
        """1 節を解釈し、該当メトリクスの範囲を設定する。"""
        numbers = self._extract_numbers(clause)
        is_range = any(sep in clause for sep in FILTER_RANGE_SEPARATORS)
        rng = self._range_for(candidate, metric)

        if len(numbers) >= 2 and is_range:
            low, high = sorted(numbers[:2])
            rng.minimum = low
            rng.maximum = high
            return

        if numbers:
            value = numbers[0]
            if self._has_max_comparator(clause):
                rng.maximum = value
            else:
                # 明示的な下限表現が無くても、数値指定は下限とみなす。
                rng.minimum = value
            return

        # 数値が無い定性表現(「多い」「少ない」)を既定しきい値へ写像する。
        threshold = FILTER_QUALITATIVE_THRESHOLDS[metric]
        if self._has_max_comparator(clause):
            rng.maximum = threshold
        elif self._has_min_comparator(clause):
            rng.minimum = threshold

    @staticmethod
    def _range_for(candidate: CandidateFilter, metric: str) -> MetricRange:
        """メトリクス名に対応する :class:`MetricRange` を返す。"""
        if metric == "followers":
            return candidate.followers
        if metric == "following":
            return candidate.following
        return candidate.posts

    @staticmethod
    def _extract_numbers(clause: str) -> list[int]:
        """節から数値(桁単位を考慮)を抽出する。"""
        values: list[int] = []
        for digits, unit in _NUMBER_PATTERN.findall(clause):
            base = float(digits.replace(",", ""))
            multiplier = FILTER_NUMBER_UNITS.get(unit, 1)
            values.append(int(base * multiplier))
        return values

    @staticmethod
    def _has_max_comparator(clause: str) -> bool:
        """上限を表す比較表現を含むか。"""
        return any(kw in clause for kw in FILTER_MAX_KEYWORDS)

    @staticmethod
    def _has_min_comparator(clause: str) -> bool:
        """下限を表す比較表現を含むか。"""
        return any(kw in clause for kw in FILTER_MIN_KEYWORDS)
