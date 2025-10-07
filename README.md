# Composer Local JP

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE) [![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![Airflow](https://img.shields.io/badge/Airflow-2.10.2-00C853?logo=apache-airflow&logoColor=white)](https://airflow.apache.org/) [![Docker](https://img.shields.io/badge/Docker-required-2496ED?logo=docker&logoColor=white)](https://www.docker.com/) ![Make](https://img.shields.io/badge/Make-required-6D4C41?logo=gnu&logoColor=white) ![Google Cloud SDK](https://img.shields.io/badge/Google%20Cloud%20SDK-required-EA4335?logo=google-cloud&logoColor=white) ![uv](https://img.shields.io/badge/uv-required-DE5FE9?logo=astral&logoColor=white)

Google Cloud Composer（Apache Airflow）のローカル開発環境を日本語で簡単に構築・運用できるCLIです。

## 特徴

- **簡単セットアップ** - `make create` 一発で完全な Airflow 環境を構築
- **Secret Manager 統合** - staging 環境の Variables を安全に同期
- **認証の柔軟性** - 個人アカウント/サービスアカウントを簡単に切り替え
- **Composer 3 対応** - 最新の Airflow 2.10.2 + PostgreSQL
- **uv による高速な依存関係管理**

> 本プロジェクトは Google LLC の [GoogleCloudPlatform/composer-local-dev](https://github.com/GoogleCloudPlatform/composer-local-dev)（Apache License 2.0）を基に、日本語環境向けに最適化したものです。


---

## クイックスタート

### 1. 初期設定

```bash
# 1. リポジトリのクローン
git clone <repository-url>
cd composer-local-jp

# 2. 設定ファイルのセットアップ
cp composer_local/composer_settings.py.example composer_local/composer_settings.py

# 3. composer_settings.py を編集して以下の値を設定
# - PROJECT_ID: あなたのGCPプロジェクトID
# - COMPOSER_ENV_NAME: Cloud Composer環境名
# - COMPOSER_LOCATION: Cloud Composer環境のリージョン
# - SERVICE_ACCOUNT: 使用するサービスアカウント
# - SECRET_ID: Airflow Variables用のSecret Manager ID
```

> **Note**
> `composer_settings.py` には実際の認証情報を入力しますが、このファイルは `.gitignore` で除外されているため、誤ってコミットされることはありません。

### 2. 環境構築と起動

```bash
# 4. 依存関係のインストール
make import

# 5. ローカル環境の作成（初回のみ）
make create

# 6. 環境を起動（フォアグラウンドで実行）
make start

# ブラウザでAirflow Web UIにアクセス
# http://localhost:8080
# ユーザー名: admin / パスワード: admin

# 停止する場合は Ctrl+C
```

> **Tip**
> `make create` は初回環境構築とセットアップを自動で行います。その後は `make start` で起動してください。

<details>
<summary>ディレクトリ構造</summary>

```
composer-local-jp/
├── .venv/                    # uv仮想環境
├── composer/                 # ローカル環境データ（gitignore）
│   └── <env-name>/
│       ├── postgresql_data/  # PostgreSQLデータ
│       ├── dags/             # DAGファイル
│       └── plugins/          # カスタムプラグイン
├── composer_local/           # ローカルCLI
└── dags/                     # DAG定義ファイル
```
</details>

---

## コマンドリファレンス

### 基本コマンド

| コマンド | 説明 |
|---------|------|
| `make create` | ローカル環境の作成と初期セットアップ（初回のみ） |
| `make start` | 環境の起動（フォアグラウンド実行、Ctrl+C で停止） |
| `make stop` | 環境の停止 |
| `make status` | 環境の状態確認 |
| `make logs` | ログの表示 |
| `make remove` | 環境の削除 |
| `make recreate` | 環境を削除して再作成 |

> **Warning**
> `make start` はフォアグラウンドで実行されます。localhostにアクセスする場合は別のターミナルを使用してください。

<details>
<summary><code>make status</code> の出力例</summary>

```bash
$ make status

Composer 環境情報

- 環境名: my-local-env
- 状態: running
- イメージバージョン: composer-3-airflow-2.10.5-build.13
- DAG ディレクトリ: /Users/username/path/to/composer-local-jp/dags
- 認証情報: サービスアカウントの権限借用
        YOUR_SERVICE_ACCOUNT@YOUR_PROJECT_ID.iam.gserviceaccount.com
- 設定パス: /Users/username/.config/gcloud
```
</details>

---

## 認証設定

認証情報の設定は `make create` の実行時に自動で行われますが、後から変更することも可能です。

| コマンド | 用途 | 使用場面 |
|---------|------|---------|
| `make auth-user` | 個人の Google アカウント | 個人開発、テスト環境 |
| `make auth-sa` | サービスアカウント権限借用 | staging と同等の権限で作業 |

> **Note**
> 認証情報を変更した後は `make start` で環境を再起動する必要はありません。環境が起動中でも即座に自動的に反映されます。

---

## DAG の追加とアップデート

- デフォルトの DAG ディレクトリ: `./composer/<env-name>/dags`
- ファイルを更新すると再起動なしで反映されます

### Airflow Variables の管理

> **Important**
> Airflow Variables は staging 環境で追加後に `make sync-vars` を実行してください。

**同期の流れ:**

1. staging 環境の Airflow で Variables を追加
2. `make sync-vars` を実行（Secret Manager から取り込み）
3. ローカルの Airflow で確認




---

## セキュリティ

### 機密情報の管理

- `composer_settings.py` は `.gitignore` で除外
- `.example` ファイルからコピーして使用
- 機密情報は GCP Secret Manager で管理

> **Warning**
> - 本ツールはローカル開発・テスト専用です
> - 管理者アカウント（admin/admin）は開発環境専用
> - サービスアカウントキーファイル（.json）を直接コミットしない

詳細は [SECURITY.md](SECURITY.md) をご確認ください。

---

## トラブルシューティング

<details>
<summary>よくある問題と解決方法</summary>

### Docker マウントエラー
```bash
make recreate
```

### PostgreSQL ポートが使用中
デフォルトポート 25432 が使用されている場合、`composer_settings.py` で変更してください。

</details>

---

## ライセンス

このプロジェクトは Apache License 2.0 でライセンスされています。詳細は [LICENSE](LICENSE) をご覧ください。


**元プロジェクト:**
本プロジェクトは Google LLC の [composer-local-dev](https://github.com/GoogleCloudPlatform/composer-local-dev) を基に作成されています。

詳細な帰属情報については [NOTICE](NOTICE) ファイルをご確認ください。

---

## 貢献

Issue や Pull Request を歓迎します。大きな変更の場合は、まず Issue で議論してください。
