"""Google Gemini API を用いた趣味・関心分析サービス。

プロフィールと投稿をまとめて送信し、決められた JSON スキーマの
特徴量プロファイルを取得する。JSON 以外を返させないようプロンプトを設計する。
"""

from __future__ import annotations

import json
from typing import Any

from google import genai
from pydantic import ValidationError

from config import GEMINI_MAX_POST_CHARS, GEMINI_MAX_POSTS_FOR_ANALYSIS
from services.schemas import FeatureProfile
from utils.logger import get_logger

logger = get_logger(__name__)

# JSON 以外を返させないための指示を含むプロンプトテンプレート。
_PROMPT_TEMPLATE = """あなたはSNSの公開情報から利用者の趣味・関心を分析するアシスタントです。
以下の公開プロフィールと公開投稿を読み、趣味・関心の特徴量を推定してください。

# 制約
- 必ず下記スキーマの **JSON のみ** を出力してください。
- JSON 以外の文章・説明・コードブロック記号(```)は一切出力しないでください。
- 各スコアは 0〜100 の整数または小数で表してください。
- ゲームタイトルや関心の種類は分析対象から適切に判断して追加してください。

# 出力スキーマ
{{
  "games": {{ "<ゲーム名>": <score> }},
  "contents": {{ "<関心の種類>": <score> }},
  "communication": {{ "social": <score>, "positive": <score>, "humor": <score> }},
  "activity": {{ "image_post_rate": <score>, "tweet_frequency": <score> }},
  "summary": "<日本語の要約>"
}}

# 分析対象
{payload}
"""


class GeminiServiceError(Exception):
    """Gemini API 連携で発生したエラーを表す例外。"""


class GeminiParseError(GeminiServiceError):
    """Gemini の応答 JSON の解析に失敗したことを表す例外。"""


class GeminiService:
    """Gemini API をラップし、特徴量プロファイルを生成するクライアント。"""

    def __init__(self, api_key: str, model_name: str) -> None:
        """クライアントを初期化する。

        Args:
            api_key: Gemini API キー。
            model_name: 使用するモデル名。

        Raises:
            GeminiServiceError: API キーが未設定の場合。
        """
        if not api_key:
            raise GeminiServiceError("GEMINI_API_KEY が設定されていません。")
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def analyze_profile(
        self, profile_text: str, posts_text: list[str]
    ) -> FeatureProfile:
        """プロフィールと投稿から特徴量プロファイルを生成する。

        Args:
            profile_text: プロフィール(自己紹介など)のテキスト。
            posts_text: 投稿本文のリスト。

        Returns:
            FeatureProfile: 解析済みの特徴量プロファイル。

        Raises:
            GeminiServiceError: API 呼び出しに失敗した場合。
            GeminiParseError: 応答の JSON 解析・検証に失敗した場合。
        """
        payload = self._build_payload(profile_text, posts_text)
        prompt = _PROMPT_TEMPLATE.format(payload=payload)
        raw = self._generate(prompt)
        return self._parse_response(raw)

    def analyze_query(self, keywords: list[str]) -> FeatureProfile:
        """ユーザーが入力したキーワードから理想の特徴量プロファイルを生成する。

        Args:
            keywords: 趣味キーワードのリスト。

        Returns:
            FeatureProfile: 入力を表す特徴量プロファイル。
        """
        joined = ", ".join(kw.strip() for kw in keywords if kw.strip())
        pseudo_profile = f"以下の趣味・関心キーワードを持つ理想的なユーザー: {joined}"
        return self.analyze_profile(pseudo_profile, [])

    def _generate(self, prompt: str) -> str:
        """Gemini へプロンプトを送信し、テキスト応答を返す。"""
        try:
            response = self._client.models.generate_content(
                model=self._model_name, contents=prompt
            )
            text = response.text
        except Exception as exc:  # noqa: BLE001 - SDK 例外を一括で捕捉しログ化する
            logger.error("Gemini API call failed: %s", exc)
            raise GeminiServiceError(f"Gemini API 呼び出しに失敗しました: {exc}") from exc

        if not text:
            logger.error("Gemini returned empty response")
            raise GeminiParseError("Gemini から空の応答が返されました。")
        return text

    @staticmethod
    def _build_payload(profile_text: str, posts_text: list[str]) -> str:
        """プロンプトへ埋め込む分析対象テキストを構築する。

        トークン節約のため、投稿は件数・1 件あたりの文字数を上限でトリムする。
        """
        trimmed: list[str] = []
        for post in posts_text:
            text = post.strip()
            if not text:
                continue
            if len(text) > GEMINI_MAX_POST_CHARS:
                text = text[:GEMINI_MAX_POST_CHARS] + "…"
            trimmed.append(text)
            if len(trimmed) >= GEMINI_MAX_POSTS_FOR_ANALYSIS:
                break
        posts_block = "\n".join(f"- {p}" for p in trimmed)
        return (
            f"## プロフィール\n{profile_text or '(なし)'}\n\n"
            f"## 投稿\n{posts_block or '(なし)'}"
        )

    @staticmethod
    def _parse_response(raw: str) -> FeatureProfile:
        """Gemini の応答テキストから JSON を抽出・検証する。

        Args:
            raw: Gemini の生応答。

        Returns:
            FeatureProfile: 検証済みプロファイル。

        Raises:
            GeminiParseError: JSON 抽出または検証に失敗した場合。
        """
        cleaned = GeminiService._strip_code_fences(raw).strip()
        try:
            data: dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Gemini JSON: %s | raw=%s", exc, raw[:300])
            raise GeminiParseError(
                f"Gemini 応答の JSON 解析に失敗しました: {exc}"
            ) from exc

        try:
            return FeatureProfile.model_validate(data)
        except ValidationError as exc:
            logger.error("Gemini JSON schema validation failed: %s", exc)
            raise GeminiParseError(
                f"Gemini 応答のスキーマ検証に失敗しました: {exc}"
            ) from exc

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """```json ... ``` のようなコードフェンスを取り除く。"""
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            # 先頭の ```json と末尾の ``` を除去する。
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines)
        return stripped
