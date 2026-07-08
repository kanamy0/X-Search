# X 趣味アカウント レコメンドツール (MVP)

X (Twitter) の**公開情報のみ**を利用して、ユーザーが入力した趣味・興味に近い公開アカウントを推薦する MVP です。

人物の特定・監視を目的とせず、公開プロフィールおよび公開投稿を分析し、趣味・関心が近いアカウントをレコメンドします。取得は X API で取得可能な公開情報に限定しています。

---

## 主な機能

- **キーワード入力**: 趣味キーワード(複数)と最大取得件数を指定して検索。
- **X API 検索**: 公開投稿を recent search で検索し、投稿・ユーザーを収集。
- **ユーザー / 投稿取得**: 公開プロフィールと最新投稿(約 20 件)を取得し SQLite に保存(重複取得は回避)。
- **Gemini 分析**: プロフィールと投稿をまとめて Google Gemini へ送信し、趣味・関心の特徴量を JSON で取得。
- **推薦ロジック**: 入力キーワードから理想の特徴量ベクトルを生成し、コサイン類似度で一致率 (0〜100%) を算出。
- **キャッシュ**: 分析済みユーザーは再分析せず、更新日時が 7 日以上前の場合のみ再分析。
- **UI**: 左に検索条件、右にカード形式のおすすめ一覧。詳細画面でプロフィール・最新投稿・Gemini 分析結果(整形 JSON)を表示。

---

## セットアップ方法

### 1. 前提

- Python 3.12 以上

### 2. 仮想環境と依存関係

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、API キーを設定します。

```bash
cp .env.example .env
```

```env
X_BEARER_TOKEN=あなたのXBearerToken
GEMINI_API_KEY=あなたのGeminiAPIキー
```

任意で `GEMINI_MODEL` / `DATABASE_URL` / `LOG_LEVEL` も設定できます。

---

## API キー取得方法

### X API (Bearer Token)

1. [X Developer Platform](https://developer.x.com/) でデベロッパーアカウントを作成。
2. Project / App を作成。
3. App の "Keys and tokens" から **Bearer Token** を発行し、`X_BEARER_TOKEN` に設定。
4. recent search / users / user tweets を利用できるプラン(アクセスレベル)が必要です。

### Google Gemini API

1. [Google AI Studio](https://aistudio.google.com/app/apikey) にアクセス。
2. API キーを発行し、`GEMINI_API_KEY` に設定。

---

## 起動方法

```bash
streamlit run app.py
```

ブラウザで表示される URL(通常 `http://localhost:8501`)にアクセスします。

1. 左サイドバーに趣味キーワード(改行またはカンマ区切り)と最大取得件数を入力。
2. 「検索」ボタンを押す。
3. 右側におすすめアカウントがカード表示されます。「詳細」で詳細画面へ。

---

## ディレクトリ構成

```
.
├── app.py                     # Streamlit エントリポイント / DI
├── config.py                  # 設定・定数の集約
├── requirements.txt
├── .env.example
├── database/
│   ├── models.py              # SQLAlchemy モデル (users / posts / analysis)
│   └── repository.py          # データアクセス層・キャッシュ判定
├── services/
│   ├── x_service.py           # X API v2 クライアント
│   ├── gemini_service.py      # Gemini 分析クライアント
│   ├── analysis_service.py    # 検索→分析→推薦のオーケストレーション
│   ├── recommend_service.py   # コサイン類似度による一致率計算
│   └── schemas.py             # 特徴量プロファイルの pydantic スキーマ
├── ui/
│   └── pages.py               # 画面描画 (検索条件 / 一覧 / 詳細)
├── utils/
│   └── logger.py              # 共通ロガー
├── tests/                     # 単体テスト (pytest)
└── README.md
```

---

## データベース (SQLite)

- **users**: `id, user_id, name, username, description, followers, following, created_at, updated_at`
- **posts**: `id, post_id, user_id, text, created_at`
- **analysis**: `id, user_id, analysis_json, similarity, updated_at`(`analysis_json` は JSON 文字列)

---

## テスト

```bash
pytest
```

外部 API に依存しないロジック(類似度計算・JSON 解析・リポジトリのキャッシュ判定)を検証します。

---

## エラー処理

以下を考慮しています。

- X API のレート制限 (HTTP 429)
- X API タイムアウト
- Gemini API エラー / 空応答
- Gemini 応答の JSON 解析失敗(コードフェンス除去・スキーマ検証)
- DB エラー

エラー発生時は原因を特定しやすいログを出力します。

---

## 今後の拡張方法

保守性・拡張性を意識した層分割(UI / サービス / データアクセス)にしています。以下を追加しやすい設計です。

- **「このアカウントに似た人を探す」**: `AnalysisService` に候補プロファイル起点の検索を追加。
- **ベクトル検索**: `recommend_service` の類似度計算を専用ベクトル DB に差し替え。
- **PostgreSQL 対応**: `DATABASE_URL` を変更するだけで SQLAlchemy が対応。
- **Docker 対応**: Dockerfile / docker-compose を追加。
- **定期クロール**: `AnalysisService` をバッチから呼び出し。
- **RAG による高度な検索**: 投稿を埋め込み化して検索文脈に利用。
- **画像分析**: 投稿画像から趣味推定を行うサービスを追加。
- **複数 SNS 対応**: `x_service` と同じインターフェースで Bluesky / Mastodon クライアントを追加。

---

## 重要事項・利用上の注意

- X の**公開情報のみ**を利用します。
- X API および Google Gemini API の利用規約を遵守してください。
- 非公開アカウントや取得権限のない情報へのアクセスは実装していません。
- API の利用可能な範囲内で動作し、取得できない情報を前提とした機能は含みません。
