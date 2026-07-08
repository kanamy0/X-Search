"""Streamlit の画面描画を担うモジュール。

左側に検索条件、右側に推薦一覧(カード表示)を配置し、
詳細画面ではプロフィール・最新投稿・Gemini 分析結果を整形表示する。
"""

from __future__ import annotations

import json

import streamlit as st

from config import (
    DEFAULT_MAX_RESULTS,
    X_SEARCH_MAX_RESULTS_LIMIT,
    X_SEARCH_MAX_RESULTS_MIN,
    Settings,
)
from services.analysis_service import AnalysisService, Recommendation, SearchOutcome

# セッションステートのキーを定数化する。
_STATE_RESULTS = "search_outcome"
_STATE_SELECTED = "selected_user_id"


def render_sidebar() -> tuple[list[str], int, bool]:
    """左側の検索条件フォームを描画する。

    Returns:
        tuple[list[str], int, bool]: (キーワード一覧, 取得件数, 検索実行フラグ)。
    """
    st.sidebar.header("検索条件")
    st.sidebar.caption("趣味・興味に近い公開アカウントを探します。")

    keywords_raw = st.sidebar.text_area(
        "趣味キーワード(改行またはカンマ区切りで複数入力)",
        value="",
        height=160,
        placeholder="DQ10\nドラクエ10\nドレア\nパシャ\nハウジング",
    )
    max_results = st.sidebar.slider(
        "最大取得件数",
        min_value=X_SEARCH_MAX_RESULTS_MIN,
        max_value=X_SEARCH_MAX_RESULTS_LIMIT,
        value=DEFAULT_MAX_RESULTS,
        step=X_SEARCH_MAX_RESULTS_MIN,
    )
    search_clicked = st.sidebar.button("検索", type="primary", use_container_width=True)

    keywords = _split_keywords(keywords_raw)
    return keywords, max_results, search_clicked


def render_results(outcome: SearchOutcome) -> None:
    """右側に推薦一覧(カード表示)を描画する。

    Args:
        outcome: 検索結果。
    """
    for warning in outcome.warnings:
        st.warning(warning)

    if not outcome.recommendations:
        st.info("検索を実行すると、ここにおすすめアカウントが表示されます。")
        return

    st.subheader(f"おすすめ一覧 ({len(outcome.recommendations)} 件)")
    for rec in outcome.recommendations:
        _render_card(rec)


def render_detail(rec: Recommendation) -> None:
    """詳細画面(プロフィール・最新投稿・分析結果)を描画する。

    Args:
        rec: 表示対象の推薦。
    """
    if st.button("← 一覧へ戻る"):
        st.session_state[_STATE_SELECTED] = None
        _rerun()

    st.header(f"{rec.name} (@{rec.username})")
    st.metric("一致率", f"{rec.match_rate:.1f}%")

    col1, col2 = st.columns(2)
    col1.metric("フォロワー数", f"{rec.followers:,}")
    col2.metric("フォロー数", f"{rec.following:,}")

    st.subheader("プロフィール")
    st.write(rec.description or "(自己紹介なし)")

    if rec.common_interests:
        st.subheader("共通趣味")
        st.write(" / ".join(rec.common_interests))

    st.subheader("最新投稿")
    if rec.latest_posts:
        for post in rec.latest_posts:
            st.markdown(f"- {post}")
    else:
        st.write("(投稿なし)")

    st.subheader("Gemini 分析結果")
    st.json(rec.analysis)
    st.download_button(
        "分析 JSON をダウンロード",
        data=json.dumps(rec.analysis, ensure_ascii=False, indent=2),
        file_name=f"analysis_{rec.username or rec.user_id}.json",
        mime="application/json",
    )


def render_missing_keys_warning(settings: Settings) -> None:
    """API キー未設定時の警告を描画する。

    Args:
        settings: アプリケーション設定。
    """
    if settings.missing_keys:
        joined = ", ".join(settings.missing_keys)
        st.error(
            f"以下の API キーが未設定です: {joined}\n\n"
            ".env を作成し、キーを設定してください(.env.example を参照)。"
        )


def run_search(service: AnalysisService, keywords: list[str], max_results: int) -> None:
    """検索を実行し、結果をセッションステートへ保存する。

    Args:
        service: 分析サービス。
        keywords: 検索キーワード。
        max_results: 最大取得件数。
    """
    with st.spinner("公開アカウントを検索・分析しています..."):
        outcome = service.search_and_recommend(keywords, max_results)
    st.session_state[_STATE_RESULTS] = outcome
    st.session_state[_STATE_SELECTED] = None


def get_selected_recommendation() -> Recommendation | None:
    """選択中の推薦を取得する。

    Returns:
        Recommendation | None: 選択されていなければ None。
    """
    selected_id = st.session_state.get(_STATE_SELECTED)
    outcome: SearchOutcome | None = st.session_state.get(_STATE_RESULTS)
    if not selected_id or outcome is None:
        return None
    for rec in outcome.recommendations:
        if rec.user_id == selected_id:
            return rec
    return None


def get_current_outcome() -> SearchOutcome:
    """現在の検索結果を取得する(未実行なら空)。

    Returns:
        SearchOutcome: 現在の検索結果。
    """
    outcome: SearchOutcome | None = st.session_state.get(_STATE_RESULTS)
    return outcome if outcome is not None else SearchOutcome()


def _render_card(rec: Recommendation) -> None:
    """推薦 1 件をカードとして描画する。"""
    with st.container(border=True):
        header_col, rate_col = st.columns([3, 1])
        header_col.markdown(f"**{rec.name}**  \n@{rec.username}")
        rate_col.metric("一致率", f"{rec.match_rate:.1f}%")

        if rec.summary:
            st.write(rec.summary)
        if rec.common_interests:
            st.caption("共通趣味: " + " / ".join(rec.common_interests))
        st.caption(f"フォロワー数: {rec.followers:,}")

        if st.button("詳細", key=f"detail_{rec.user_id}"):
            st.session_state[_STATE_SELECTED] = rec.user_id
            _rerun()


def _split_keywords(raw: str) -> list[str]:
    """改行・カンマ区切りの入力をキーワードのリストへ変換する。"""
    tokens = raw.replace(",", "\n").replace("、", "\n").splitlines()
    return [token.strip() for token in tokens if token.strip()]


def _rerun() -> None:
    """Streamlit のバージョン差異を吸収して再実行する。"""
    st.rerun()
