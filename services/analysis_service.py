"""検索から推薦までの一連のパイプラインを統括するサービス。

X からの取得・DB 保存・Gemini 分析(キャッシュ制御)・一致率計算を
オーケストレーションし、UI へ渡す推薦結果を組み立てる。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from config import DEFAULT_MAX_RESULTS, X_USER_TWEETS_COUNT
from database.repository import Repository
from services.gemini_service import GeminiParseError, GeminiService, GeminiServiceError
from services.recommend_service import RecommendService
from services.schemas import FeatureProfile
from services.x_service import XRateLimitError, XService, XServiceError
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Recommendation:
    """UI 表示用の推薦 1 件を表すデータ構造。"""

    user_id: str
    name: str
    username: str
    description: str
    followers: int
    following: int
    match_rate: float
    summary: str
    common_interests: list[str]
    analysis: dict[str, object] = field(default_factory=dict)
    latest_posts: list[str] = field(default_factory=list)


@dataclass
class SearchOutcome:
    """検索処理の結果と、処理中に発生した警告をまとめた構造。"""

    recommendations: list[Recommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class AnalysisService:
    """検索・分析・推薦のパイプラインを実行するサービス。"""

    def __init__(
        self,
        x_service: XService,
        gemini_service: GeminiService,
        repository: Repository,
        recommend_service: RecommendService,
    ) -> None:
        """依存サービスを注入して初期化する。

        Args:
            x_service: X API クライアント。
            gemini_service: Gemini 分析クライアント。
            repository: 永続化リポジトリ。
            recommend_service: 類似度計算サービス。
        """
        self._x = x_service
        self._gemini = gemini_service
        self._repo = repository
        self._recommender = recommend_service

    def search_and_recommend(
        self, keywords: list[str], max_results: int = DEFAULT_MAX_RESULTS
    ) -> SearchOutcome:
        """キーワードから公開アカウントを検索・分析し、推薦一覧を返す。

        Args:
            keywords: 趣味キーワードのリスト。
            max_results: 検索で取得する最大投稿件数。

        Returns:
            SearchOutcome: 一致率の高い順に並んだ推薦結果と警告。
        """
        outcome = SearchOutcome()

        # 1) 入力キーワードを理想プロファイルへ変換する。
        try:
            query_profile = self._gemini.analyze_query(keywords)
        except (GeminiServiceError, GeminiParseError) as exc:
            logger.error("Failed to analyze query keywords: %s", exc)
            outcome.warnings.append(f"入力キーワードの分析に失敗しました: {exc}")
            return outcome

        # 2) 公開投稿を検索する。
        try:
            posts = self._x.search_recent_posts(keywords, max_results)
        except XRateLimitError as exc:
            outcome.warnings.append(str(exc))
            return outcome
        except XServiceError as exc:
            logger.error("X search failed: %s", exc)
            outcome.warnings.append(f"X 検索に失敗しました: {exc}")
            return outcome

        if not posts:
            outcome.warnings.append("該当する公開投稿が見つかりませんでした。")
            return outcome

        # 3) 投稿主のユーザー ID を収集し、プロフィールを取得・保存する。
        user_ids = list({p["user_id"] for p in posts if p["user_id"]})
        try:
            users = self._x.get_users(user_ids)
        except XServiceError as exc:
            logger.error("Fetching users failed: %s", exc)
            outcome.warnings.append(f"ユーザー情報の取得に失敗しました: {exc}")
            return outcome

        self._repo.save_posts(posts)
        for user in users:
            self._repo.upsert_user(user)

        # 4) 各ユーザーを分析し、一致率を算出する。
        for user in users:
            try:
                recommendation = self._analyze_user(user, query_profile)
            except XRateLimitError as exc:
                outcome.warnings.append(str(exc))
                break
            except (GeminiServiceError, GeminiParseError, XServiceError) as exc:
                logger.warning(
                    "Skipping user_id=%s due to error: %s", user["user_id"], exc
                )
                outcome.warnings.append(
                    f"@{user.get('username', user['user_id'])} の分析をスキップしました: {exc}"
                )
                continue
            if recommendation is not None:
                outcome.recommendations.append(recommendation)

        outcome.recommendations.sort(key=lambda r: r.match_rate, reverse=True)
        return outcome

    def _analyze_user(
        self, user: dict[str, object], query_profile: FeatureProfile
    ) -> Recommendation | None:
        """1 ユーザーを分析(必要なら再分析)して推薦を組み立てる。

        Args:
            user: ユーザープロフィール辞書。
            query_profile: 入力から生成した理想プロファイル。

        Returns:
            Recommendation | None: 組み立てた推薦。
        """
        user_id = str(user["user_id"])

        # 最新投稿を取得・保存(重複は repository 側で除外)。
        posts = self._x.get_user_tweets(user_id, X_USER_TWEETS_COUNT)
        if posts:
            self._repo.save_posts(posts)
        stored_posts = self._repo.get_posts_for_user(user_id)
        posts_text = [p.text for p in stored_posts]

        profile = self._get_or_create_analysis(user, posts_text)

        match_rate = self._recommender.match_rate(query_profile, profile)
        common = self._recommender.common_interests(query_profile, profile)
        # 一致率を最新の値で保存し直す(入力ごとに変わるため)。
        self._repo.save_analysis(
            user_id, profile.model_dump_json(), match_rate
        )

        return Recommendation(
            user_id=user_id,
            name=str(user.get("name", "")),
            username=str(user.get("username", "")),
            description=str(user.get("description", "")),
            followers=int(user.get("followers", 0) or 0),
            following=int(user.get("following", 0) or 0),
            match_rate=round(match_rate, 1),
            summary=profile.summary,
            common_interests=common,
            analysis=profile.model_dump(),
            latest_posts=posts_text[:X_USER_TWEETS_COUNT],
        )

    def _get_or_create_analysis(
        self, user: dict[str, object], posts_text: list[str]
    ) -> FeatureProfile:
        """分析キャッシュを参照し、有効ならそれを、なければ再分析して返す。

        Args:
            user: ユーザープロフィール辞書。
            posts_text: 投稿本文のリスト。

        Returns:
            FeatureProfile: 特徴量プロファイル。
        """
        user_id = str(user["user_id"])
        if self._repo.is_analysis_fresh(user_id):
            cached = self._repo.get_analysis(user_id)
            if cached is not None:
                logger.info("Using cached analysis for user_id=%s", user_id)
                try:
                    data = json.loads(cached.analysis_json)
                    return FeatureProfile.model_validate(data)
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.warning(
                        "Cached analysis invalid for user_id=%s, re-analyzing: %s",
                        user_id,
                        exc,
                    )

        logger.info("Analyzing user_id=%s with Gemini", user_id)
        return self._gemini.analyze_profile(
            str(user.get("description", "")), posts_text
        )
