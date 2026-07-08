"""Streamlit アプリケーションのエントリポイント。

依存サービスの組み立て(DI)と画面遷移の制御を行う。
実行: `streamlit run app.py`
"""

from __future__ import annotations

import streamlit as st

from config import Settings, get_settings
from database.models import create_db_engine, create_session_factory
from database.repository import Repository
from services.analysis_service import AnalysisService
from services.gemini_service import GeminiService
from services.recommend_service import RecommendService
from services.x_service import XService
from ui import pages
from utils.logger import get_logger

logger = get_logger(__name__)

_PAGE_TITLE = "X 趣味アカウント レコメンド"


@st.cache_resource(show_spinner=False)
def _build_service(settings: Settings) -> AnalysisService | None:
    """設定から分析サービスを構築する(リソースはキャッシュ)。

    Args:
        settings: アプリケーション設定。

    Returns:
        AnalysisService | None: API キー不足時は None。
    """
    if settings.missing_keys:
        return None

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    repository = Repository(session_factory)

    x_service = XService(settings.x_bearer_token)
    gemini_service = GeminiService(settings.gemini_api_key, settings.gemini_model)
    recommend_service = RecommendService()

    return AnalysisService(
        x_service=x_service,
        gemini_service=gemini_service,
        repository=repository,
        recommend_service=recommend_service,
    )


def main() -> None:
    """アプリケーションのメインルーチン。"""
    st.set_page_config(page_title=_PAGE_TITLE, layout="wide")
    st.title(_PAGE_TITLE)
    st.caption("X の公開情報のみを利用し、趣味・関心の近い公開アカウントを推薦します。")

    settings = get_settings()
    pages.render_missing_keys_warning(settings)

    keywords, max_results, filter_text, search_clicked = pages.render_sidebar()

    service = _build_service(settings)

    if search_clicked:
        if service is None:
            st.error("API キーが未設定のため検索を実行できません。")
        elif not keywords:
            st.warning("キーワードを 1 つ以上入力してください。")
        else:
            try:
                pages.run_search(service, keywords, max_results, filter_text)
            except Exception as exc:  # noqa: BLE001 - UI では全例外を表示に変換する
                logger.exception("Unexpected error during search")
                st.error(f"予期しないエラーが発生しました: {exc}")

    selected = pages.get_selected_recommendation()
    if selected is not None:
        pages.render_detail(selected)
    else:
        pages.render_results(pages.get_current_outcome())


if __name__ == "__main__":
    main()
