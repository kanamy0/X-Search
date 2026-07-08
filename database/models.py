"""SQLAlchemy による ORM モデル定義。

SQLite を対象とするが、将来的な PostgreSQL 対応を見据えて
`DATABASE_URL` から接続先を切り替えられる設計とする。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from config import get_settings


def _utcnow() -> datetime:
    """タイムゾーン付き(UTC)の現在時刻を返す。"""
    return datetime.now(tz=timezone.utc)


class Base(DeclarativeBase):
    """全モデルの基底クラス。"""


class User(Base):
    """X の公開ユーザープロフィールを表すモデル。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    username: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    followers: Mapped[int] = mapped_column(Integer, default=0)
    following: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    posts: Mapped[list["Post"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class Post(Base):
    """X の公開投稿を表すモデル。"""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), index=True
    )
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="posts")


class Analysis(Base):
    """Gemini による分析結果と入力との類似度を保持するモデル。"""

    __tablename__ = "analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), unique=True, index=True
    )
    # 特徴量ベクトルなどを含む JSON を文字列として保存する。
    analysis_json: Mapped[str] = mapped_column(Text, default="{}")
    similarity: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    user: Mapped["User"] = relationship(back_populates="analysis")


def create_db_engine(database_url: str | None = None) -> Engine:
    """データベースエンジンを生成する。

    Args:
        database_url: 接続 URL。未指定時は設定値を使用する。

    Returns:
        Engine: SQLAlchemy エンジン。
    """
    url = database_url or get_settings().database_url
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        # Streamlit の複数スレッドからの利用に備える。
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """セッションファクトリを生成し、スキーマを初期化する。

    Args:
        engine: 対象のエンジン。

    Returns:
        sessionmaker[Session]: セッションファクトリ。
    """
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
