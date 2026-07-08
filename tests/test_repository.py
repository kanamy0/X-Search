"""Repository の単体テスト(インメモリ SQLite を使用)。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from database.models import create_db_engine, create_session_factory
from database.repository import Repository


@pytest.fixture()
def repo() -> Repository:
    engine = create_db_engine("sqlite:///:memory:")
    session_factory = create_session_factory(engine)
    return Repository(session_factory)


def _user(user_id: str = "u1") -> dict[str, object]:
    return {
        "user_id": user_id,
        "name": "テスト",
        "username": "test_user",
        "description": "DQ10好き",
        "followers": 100,
        "following": 50,
        "created_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
    }


def test_upsert_user_creates_and_updates(repo: Repository) -> None:
    repo.upsert_user(_user())
    stored = repo.get_user("u1")
    assert stored is not None
    assert stored.followers == 100

    updated = _user()
    updated["followers"] = 200
    repo.upsert_user(updated)
    assert repo.get_user("u1").followers == 200  # type: ignore[union-attr]


def test_save_posts_avoids_duplicates(repo: Repository) -> None:
    posts = [
        {"post_id": "p1", "user_id": "u1", "text": "a", "created_at": None},
        {"post_id": "p2", "user_id": "u1", "text": "b", "created_at": None},
    ]
    assert repo.save_posts(posts) == 2
    # 再保存しても重複は追加されない。
    assert repo.save_posts(posts) == 0
    assert len(repo.get_posts_for_user("u1")) == 2


def test_analysis_cache_freshness(repo: Repository) -> None:
    repo.upsert_user(_user())
    repo.save_analysis("u1", "{}", 50.0)
    assert repo.is_analysis_fresh("u1") is True
    # 存在しないユーザーは fresh でない。
    assert repo.is_analysis_fresh("unknown") is False


def test_analysis_cache_expires(repo: Repository) -> None:
    repo.upsert_user(_user())
    analysis = repo.save_analysis("u1", "{}", 50.0)
    # 更新日時を 8 日前に書き換えてキャッシュ切れを再現する。
    with repo._session_factory() as session:  # type: ignore[attr-defined]
        obj = session.get(type(analysis), analysis.id)
        obj.updated_at = datetime.now(tz=timezone.utc) - timedelta(days=8)
        session.commit()
    assert repo.is_analysis_fresh("u1") is False
