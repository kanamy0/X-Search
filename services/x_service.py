"""X (Twitter) API v2 との連携を担うサービス。

公開情報(公開投稿・公開プロフィール)のみを取得する。
非公開アカウントや取得権限のない情報へはアクセスしない。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from config import (
    X_API_BASE_URL,
    X_API_TIMEOUT_SECONDS,
    X_SEARCH_MAX_RESULTS_LIMIT,
    X_SEARCH_MAX_RESULTS_MIN,
    X_USER_TWEETS_MAX,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class XServiceError(Exception):
    """X API 連携で発生したエラーを表す例外。"""


class XRateLimitError(XServiceError):
    """X API のレート制限(HTTP 429)を表す例外。"""


class XService:
    """X API v2 のエンドポイントを薄くラップするクライアント。"""

    # 検索・ユーザー取得で要求するフィールド群。
    _USER_FIELDS = "description,public_metrics,created_at,name,username"
    _TWEET_FIELDS = "created_at,author_id"

    def __init__(self, bearer_token: str, base_url: str = X_API_BASE_URL) -> None:
        """クライアントを初期化する。

        Args:
            bearer_token: X API v2 の Bearer Token。
            base_url: API のベース URL。

        Raises:
            XServiceError: Bearer Token が未設定の場合。
        """
        if not bearer_token:
            raise XServiceError("X_BEARER_TOKEN が設定されていません。")
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {bearer_token}"})

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET リクエストを送信し、JSON を返す共通処理。

        Args:
            path: エンドポイントのパス(先頭に `/`)。
            params: クエリパラメータ。

        Returns:
            dict[str, Any]: レスポンス JSON。

        Raises:
            XRateLimitError: レート制限に達した場合。
            XServiceError: タイムアウトやその他の HTTP エラー。
        """
        url = f"{self._base_url}{path}"
        try:
            response = self._session.get(
                url, params=params, timeout=X_API_TIMEOUT_SECONDS
            )
        except requests.Timeout as exc:
            logger.error("X API timeout: url=%s error=%s", url, exc)
            raise XServiceError(f"X API がタイムアウトしました: {url}") from exc
        except requests.RequestException as exc:
            logger.error("X API request failed: url=%s error=%s", url, exc)
            raise XServiceError(f"X API リクエストに失敗しました: {exc}") from exc

        if response.status_code == 429:
            logger.warning("X API rate limit reached: url=%s", url)
            raise XRateLimitError(
                "X API のレート制限に達しました。時間をおいて再試行してください。"
            )
        if not response.ok:
            logger.error(
                "X API error: url=%s status=%s body=%s",
                url,
                response.status_code,
                response.text[:500],
            )
            raise XServiceError(
                f"X API エラー (status={response.status_code}): {response.text[:200]}"
            )
        return response.json()

    def search_recent_posts(
        self, keywords: list[str], max_results: int
    ) -> list[dict[str, Any]]:
        """キーワードで公開投稿を検索する(recent search)。

        Args:
            keywords: 検索キーワードのリスト(OR 結合される)。
            max_results: 取得する最大件数。

        Returns:
            list[dict[str, Any]]: 各投稿の {post_id, created_at, user_id, text}。
        """
        query = self._build_query(keywords)
        capped = max(
            X_SEARCH_MAX_RESULTS_MIN,
            min(max_results, X_SEARCH_MAX_RESULTS_LIMIT),
        )
        params: dict[str, Any] = {
            "query": query,
            "max_results": capped,
            "tweet.fields": self._TWEET_FIELDS,
        }
        logger.info("Searching X: query=%r max_results=%d", query, capped)
        data = self._request("/tweets/search/recent", params)

        posts: list[dict[str, Any]] = []
        for tweet in data.get("data", []):
            posts.append(
                {
                    "post_id": str(tweet["id"]),
                    "created_at": self._parse_datetime(tweet.get("created_at")),
                    "user_id": str(tweet.get("author_id", "")),
                    "text": tweet.get("text", ""),
                }
            )
        logger.info("Search returned %d posts", len(posts))
        return posts

    def get_users(self, user_ids: list[str]) -> list[dict[str, Any]]:
        """ユーザー ID のリストから公開プロフィールを取得する。

        Args:
            user_ids: 取得対象のユーザー ID(最大 100 件ずつ処理)。

        Returns:
            list[dict[str, Any]]: 各ユーザーのプロフィール辞書。
        """
        results: list[dict[str, Any]] = []
        unique_ids = [uid for uid in dict.fromkeys(user_ids) if uid]
        # /users エンドポイントは 1 リクエストあたり最大 100 件。
        batch_size = 100
        for start in range(0, len(unique_ids), batch_size):
            batch = unique_ids[start : start + batch_size]
            params = {"ids": ",".join(batch), "user.fields": self._USER_FIELDS}
            data = self._request("/users", params)
            for user in data.get("data", []):
                results.append(self._parse_user(user))
        logger.info("Fetched %d user profiles", len(results))
        return results

    def get_user_tweets(
        self, user_id: str, count: int
    ) -> list[dict[str, Any]]:
        """特定ユーザーの最新公開投稿を取得する。

        Args:
            user_id: 対象ユーザーの ID。
            count: 取得件数。

        Returns:
            list[dict[str, Any]]: 各投稿の {post_id, created_at, user_id, text}。
        """
        capped = max(
            X_SEARCH_MAX_RESULTS_MIN, min(count, X_USER_TWEETS_MAX)
        )
        params: dict[str, Any] = {
            "max_results": capped,
            "tweet.fields": self._TWEET_FIELDS,
            "exclude": "retweets,replies",
        }
        data = self._request(f"/users/{user_id}/tweets", params)
        posts: list[dict[str, Any]] = []
        for tweet in data.get("data", []):
            posts.append(
                {
                    "post_id": str(tweet["id"]),
                    "created_at": self._parse_datetime(tweet.get("created_at")),
                    "user_id": user_id,
                    "text": tweet.get("text", ""),
                }
            )
        return posts

    @staticmethod
    def _build_query(keywords: list[str]) -> str:
        """キーワードのリストから recent search 用クエリを構築する。

        非公開情報を含めないよう、公開言語投稿かつリツイート除外の条件を付ける。
        """
        cleaned = [kw.strip() for kw in keywords if kw.strip()]
        if not cleaned:
            raise XServiceError("検索キーワードが指定されていません。")
        # 各キーワードを OR で結合し、リツイートを除外する。
        joined = " OR ".join(f'"{kw}"' if " " in kw else kw for kw in cleaned)
        return f"({joined}) -is:retweet"

    @staticmethod
    def _parse_user(user: dict[str, Any]) -> dict[str, Any]:
        """API レスポンスのユーザーオブジェクトを内部辞書へ変換する。"""
        metrics = user.get("public_metrics", {})
        return {
            "user_id": str(user["id"]),
            "name": user.get("name", ""),
            "username": user.get("username", ""),
            "description": user.get("description", ""),
            "followers": int(metrics.get("followers_count", 0)),
            "following": int(metrics.get("following_count", 0)),
            "posts_count": int(metrics.get("tweet_count", 0)),
            "created_at": XService._parse_datetime(user.get("created_at")),
        }

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        """ISO8601 文字列を datetime へ変換する(失敗時は None)。"""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Failed to parse datetime: %r", value)
            return None
