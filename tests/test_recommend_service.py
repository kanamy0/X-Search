"""RecommendService の単体テスト。"""

from __future__ import annotations

import pytest

from services.recommend_service import RecommendService
from services.schemas import FeatureProfile


def _profile(games: dict[str, float], contents: dict[str, float]) -> FeatureProfile:
    return FeatureProfile(games=games, contents=contents)


def test_match_rate_identical_profiles_is_full() -> None:
    service = RecommendService()
    profile = _profile({"dq10": 95}, {"dressup": 90})
    assert service.match_rate(profile, profile) == pytest.approx(100.0)


def test_match_rate_disjoint_profiles_is_zero() -> None:
    service = RecommendService()
    query = _profile({"dq10": 95}, {})
    candidate = _profile({"ff14": 95}, {})
    assert service.match_rate(query, candidate) == 0.0


def test_match_rate_empty_candidate_is_zero() -> None:
    service = RecommendService()
    query = _profile({"dq10": 95}, {"dressup": 90})
    candidate = FeatureProfile()
    assert service.match_rate(query, candidate) == 0.0


def test_match_rate_is_within_bounds() -> None:
    service = RecommendService()
    query = _profile({"dq10": 95}, {"dressup": 90, "photo": 88})
    candidate = _profile({"dq10": 40}, {"dressup": 30})
    rate = service.match_rate(query, candidate)
    assert 0.0 <= rate <= 100.0


def test_common_interests_extracts_shared_labels() -> None:
    service = RecommendService()
    query = _profile({"dq10": 95}, {"dressup": 90})
    candidate = _profile({"dq10": 50}, {"dressup": 20, "battle": 80})
    common = service.common_interests(query, candidate)
    assert "dq10" in common
    assert "dressup" in common
    assert "battle" not in common
