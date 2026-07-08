"""GeminiService の応答解析ロジックの単体テスト(API 非依存)。"""

from __future__ import annotations

import pytest

from services.gemini_service import GeminiParseError, GeminiService

_VALID_JSON = """{
  "games": {"dq10": 95},
  "contents": {"dressup": 90, "photo": 88},
  "communication": {"social": 90, "positive": 95, "humor": 60},
  "activity": {"image_post_rate": 75, "tweet_frequency": 80},
  "summary": "DQ10のドレア好き"
}"""


def test_parse_valid_json() -> None:
    profile = GeminiService._parse_response(_VALID_JSON)
    assert profile.games["dq10"] == 95
    assert profile.summary == "DQ10のドレア好き"


def test_parse_json_with_code_fence() -> None:
    fenced = f"```json\n{_VALID_JSON}\n```"
    profile = GeminiService._parse_response(fenced)
    assert profile.contents["photo"] == 88


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(GeminiParseError):
        GeminiService._parse_response("これはJSONではありません")


def test_feature_dict_flattens_with_prefixes() -> None:
    profile = GeminiService._parse_response(_VALID_JSON)
    flat = profile.feature_dict()
    assert flat["games.dq10"] == 95
    assert flat["contents.photo"] == 88
    assert "summary" not in flat
