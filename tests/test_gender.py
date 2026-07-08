"""性別推定に関する単体テスト(API 非依存)。"""

from __future__ import annotations

from config import GENDER_FEMALE, GENDER_MALE, GENDER_UNKNOWN, gender_label
from services.gemini_service import GeminiService
from services.schemas import FeatureProfile

_JSON_WITH_GENDER = """{
  "games": {"dq10": 95},
  "contents": {"dressup": 90},
  "communication": {"social": 90, "positive": 95, "humor": 60},
  "activity": {"image_post_rate": 75, "tweet_frequency": 80},
  "gender": "female",
  "gender_confidence": 82,
  "summary": "DQ10のドレア好き"
}"""


def test_parse_gender_fields() -> None:
    profile = GeminiService._parse_response(_JSON_WITH_GENDER)
    assert profile.gender == GENDER_FEMALE
    assert profile.gender_confidence == 82


def test_gender_defaults_to_unknown_when_absent() -> None:
    profile = FeatureProfile.model_validate({"games": {"dq10": 95}})
    assert profile.gender == GENDER_UNKNOWN
    assert profile.gender_confidence == 0.0


def test_unexpected_gender_normalized_to_unknown() -> None:
    profile = FeatureProfile.model_validate({"gender": "男性"})
    assert profile.gender == GENDER_UNKNOWN


def test_gender_value_is_lowercased() -> None:
    profile = FeatureProfile.model_validate({"gender": "MALE"})
    assert profile.gender == GENDER_MALE


def test_gender_not_included_in_feature_vector() -> None:
    profile = GeminiService._parse_response(_JSON_WITH_GENDER)
    flat = profile.feature_dict()
    assert not any(key.startswith("gender") for key in flat)


def test_gender_label_maps_known_values() -> None:
    assert gender_label(GENDER_MALE) == "男性"
    assert gender_label(GENDER_FEMALE) == "女性"
    assert gender_label(GENDER_UNKNOWN) == "不明"


def test_gender_label_falls_back_to_unknown() -> None:
    assert gender_label("nonexistent") == "不明"
