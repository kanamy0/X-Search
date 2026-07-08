"""データアクセスを担うリポジトリ層。

サービス層から DB 操作の詳細を隠蔽し、重複取得の回避や
キャッシュ判定(更新日時ベース)などの永続化ロジックを提供する。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from config import ANALYSIS_CACHE_TTL_DAYS
from database.models import Analysis, Post, User
from utils.logger import get_logger

logger = get_logger(__name__)


class Repository:
    """SQLAlchemy セッションを介した永続化操作をまとめたクラス。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """リポジトリを初期化する。

        Args:
            session_factory: セッションファクトリ。
        """
        self._session_factory = session_factory

    def upsert_user(self, user_data: dict[str, object]) -> User:
        """ユーザー情報を作成または更新する。

        Args:
            user_data: `User` の各カラムに対応するキーを持つ辞書。

        Returns:
            User: 保存済みのユーザー。
        """
        with self._session_factory() as session:
            user = self._get_user(session, str(user_data["user_id"]))
            if user is None:
                user = User(user_id=str(user_data["user_id"]))
                session.add(user)

            user.name = str(user_data.get("name", ""))
            user.username = str(user_data.get("username", ""))
            user.description = str(user_data.get("description", ""))
            user.followers = int(user_data.get("followers", 0) or 0)
            user.following = int(user_data.get("following", 0) or 0)
            created = user_data.get("created_at")
            if isinstance(created, datetime):
                user.created_at = created

            session.commit()
            session.refresh(user)
            logger.debug("Upserted user user_id=%s", user.user_id)
            return user

    def save_posts(self, posts: list[dict[str, object]]) -> int:
        """投稿を重複を避けて保存する。

        Args:
            posts: `Post` のカラムに対応するキーを持つ辞書のリスト。

        Returns:
            int: 新規に保存した投稿件数。
        """
        saved = 0
        with self._session_factory() as session:
            for post_data in posts:
                post_id = str(post_data["post_id"])
                exists = session.scalar(
                    select(Post).where(Post.post_id == post_id)
                )
                if exists is not None:
                    continue
                created = post_data.get("created_at")
                session.add(
                    Post(
                        post_id=post_id,
                        user_id=str(post_data["user_id"]),
                        text=str(post_data.get("text", "")),
                        created_at=created if isinstance(created, datetime) else None,
                    )
                )
                saved += 1
            session.commit()
        logger.debug("Saved %d new posts (of %d)", saved, len(posts))
        return saved

    def get_posts_for_user(self, user_id: str) -> list[Post]:
        """指定ユーザーの投稿を取得する。

        Args:
            user_id: 対象ユーザーの X ユーザー ID。

        Returns:
            list[Post]: 投稿のリスト(新しい順)。
        """
        with self._session_factory() as session:
            stmt = (
                select(Post)
                .where(Post.user_id == user_id)
                .order_by(Post.created_at.desc().nullslast())
            )
            return list(session.scalars(stmt).all())

    def get_user(self, user_id: str) -> User | None:
        """ユーザーを取得する。

        Args:
            user_id: 対象ユーザーの X ユーザー ID。

        Returns:
            User | None: 見つからなければ None。
        """
        with self._session_factory() as session:
            return self._get_user(session, user_id)

    def save_analysis(
        self, user_id: str, analysis_json: str, similarity: float
    ) -> Analysis:
        """分析結果を作成または更新する。

        Args:
            user_id: 対象ユーザーの X ユーザー ID。
            analysis_json: Gemini 分析結果の JSON 文字列。
            similarity: 入力との一致率(0-100)。

        Returns:
            Analysis: 保存済みの分析結果。
        """
        with self._session_factory() as session:
            analysis = session.scalar(
                select(Analysis).where(Analysis.user_id == user_id)
            )
            if analysis is None:
                analysis = Analysis(user_id=user_id)
                session.add(analysis)
            analysis.analysis_json = analysis_json
            analysis.similarity = similarity
            session.commit()
            session.refresh(analysis)
            return analysis

    def get_analysis(self, user_id: str) -> Analysis | None:
        """分析結果を取得する。

        Args:
            user_id: 対象ユーザーの X ユーザー ID。

        Returns:
            Analysis | None: 見つからなければ None。
        """
        with self._session_factory() as session:
            return session.scalar(
                select(Analysis).where(Analysis.user_id == user_id)
            )

    def is_analysis_fresh(self, user_id: str) -> bool:
        """分析キャッシュが有効(TTL 内)かどうかを判定する。

        Args:
            user_id: 対象ユーザーの X ユーザー ID。

        Returns:
            bool: 有効な分析が存在すれば True。
        """
        analysis = self.get_analysis(user_id)
        if analysis is None:
            return False
        threshold = datetime.now(tz=timezone.utc) - timedelta(
            days=ANALYSIS_CACHE_TTL_DAYS
        )
        updated_at = analysis.updated_at
        # SQLite から取得した naive datetime を UTC とみなして比較する。
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return updated_at >= threshold

    @staticmethod
    def _get_user(session: Session, user_id: str) -> User | None:
        """セッション内でユーザーを取得する内部ヘルパー。"""
        return session.scalar(select(User).where(User.user_id == user_id))
