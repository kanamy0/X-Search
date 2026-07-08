"""FilterParser の単体テスト。"""

from __future__ import annotations

from services.filter_service import FilterParser


def test_empty_text_yields_empty_filter() -> None:
    parser = FilterParser()
    candidate, unparsed = parser.parse("")
    assert candidate.is_empty
    assert unparsed == []


def test_followers_minimum_with_number() -> None:
    parser = FilterParser()
    candidate, _ = parser.parse("フォロワー1000人以上")
    assert candidate.followers.minimum == 1000
    assert candidate.followers.maximum is None


def test_bare_number_is_treated_as_minimum() -> None:
    parser = FilterParser()
    candidate, _ = parser.parse("フォロワー500")
    assert candidate.followers.minimum == 500


def test_following_maximum_with_number() -> None:
    parser = FilterParser()
    candidate, _ = parser.parse("フォロー500以下")
    # 「フォロワー」ではなく「フォロー」に解釈される。
    assert candidate.following.maximum == 500
    assert candidate.followers.is_empty


def test_number_unit_man_is_expanded() -> None:
    parser = FilterParser()
    candidate, _ = parser.parse("フォロワー1万以上")
    assert candidate.followers.minimum == 10000


def test_qualitative_many_posts_maps_to_threshold() -> None:
    parser = FilterParser()
    candidate, _ = parser.parse("投稿が多い人")
    assert candidate.posts.minimum == 1000


def test_qualitative_few_followers_maps_to_max() -> None:
    parser = FilterParser()
    candidate, _ = parser.parse("フォロワーが少ない")
    assert candidate.followers.maximum == 1000


def test_range_expression() -> None:
    parser = FilterParser()
    candidate, _ = parser.parse("フォロワー1000〜5000")
    assert candidate.followers.minimum == 1000
    assert candidate.followers.maximum == 5000


def test_multiple_clauses_combined() -> None:
    parser = FilterParser()
    candidate, unparsed = parser.parse("フォロワー1000人以上、投稿が多い人")
    assert candidate.followers.minimum == 1000
    assert candidate.posts.minimum == 1000
    assert unparsed == []


def test_unrecognized_clause_reported() -> None:
    parser = FilterParser()
    candidate, unparsed = parser.parse("面白い人")
    assert candidate.is_empty
    assert unparsed == ["面白い人"]


def test_matches_applies_all_conditions() -> None:
    parser = FilterParser()
    candidate, _ = parser.parse("フォロワー1000以上、フォロー500以下")
    assert candidate.matches(followers=1500, following=200, posts=0)
    assert not candidate.matches(followers=1500, following=800, posts=0)
    assert not candidate.matches(followers=500, following=200, posts=0)


def test_describe_is_human_readable() -> None:
    parser = FilterParser()
    candidate, _ = parser.parse("フォロワー1000人以上")
    assert "フォロワー数" in candidate.describe()
    assert "1,000" in candidate.describe()
