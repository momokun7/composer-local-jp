# Composer Local JP

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE) [![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![Airflow](https://img.shields.io/badge/Airflow-2.10.2-00C853?logo=apache-airflow&logoColor=white)](https://airflow.apache.org/) [![Docker](https://img.shields.io/badge/Docker-required-2496ED?logo=docker&logoColor=white)](https://www.docker.com/) ![Make](https://img.shields.io/badge/Make-required-6D4C41?logo=gnu&logoColor=white) ![uv](https://img.shields.io/badge/uv-required-DE5FE9?logo=astral&logoColor=white)

Google Cloud Composer（Apache Airflow）のローカル開発環境を日本語で簡単に構築・運用できるCLIです。

## 特徴

- **ローカルファースト** - GCP 設定不要で `make import && make start` だけで Airflow が動く
- **簡単セットアップ** - `make start` 一発で完全な Airflow 環境を構築（初回は自動作成）
- **GCP 連携はオプション** - Secret Manager・staging 同期が必要な場合のみ設定
- **Composer 3 対応** - 最新の Airflow 2.10.5 + PostgreSQL
- **uv による高速な依存関係管理**

> 本プロジェクトは Google LLC の [GoogleCloudPlatform/composer-local-dev](https://github.com/GoogleCloudPlatform/composer-local-dev)（Apache License 2.0）を基に、日本語環境向けに最適化したものです。

---

## 前提条件

以下のツールがインストールされている必要があります。

| ツール | 確認コマンド | インストール |
|--------|-------------|-------------|
| **Docker** | `docker --version` | [Docker Desktop](https://docs.docker.com/get-docker/) |
| **Make** | `make --version` | macOS: Xcode CLT に同梱 / Linux: `apt install make` |
| **Python 3.11+** | `python3 --version` | [python.org](https://www.python.org/downloads/) |
| **uv** | `uv --version` | [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |
| **Git** | `git --version` | [git-scm.com](https://git-scm.com/downloads) |

**システム要件:**
- メモリ: **4GB 以上**推奨（Docker Desktop に割り当て）
- ディスク: **5GB 以上**の空き容量（Docker イメージ + データ）

> GCP 連携する場合のみ追加で [gcloud CLI](https://cloud.google.com/sdk/docs/install) が必要です。

---

## クイックスタート

```bash
# 1. リポジトリのクローン
git clone <repository-url>
cd composer-local-jp

# 2. 依存関係のインストール（uv sync を実行）
make import

# 3. 起動（初回は環境作成 + セットアップも自動実行）
make start
```

起動が完了すると、ターミナルにログが流れ続けます（フォアグラウンド実行）。ログが流れ続ける状態が起動完了のサインです。

> **別のターミナルを開いて** ブラウザで Airflow Web UI にアクセスしてください:
>
> **http://localhost:8080**
>
> ログイン不要です（`AUTH_ROLE_PUBLIC` が設定済みのため、認証なしでアクセスできます）。

停止するには `Ctrl+C` を押してください。

> **Tip**: GCP の設定や `composer_settings.py` のコピーは不要です。デフォルト値で動作します。

### 設定のカスタマイズ（任意）

ポートやイメージバージョンを変更したい場合:

```bash
cp composer_local/composer_settings.py.example composer_local/composer_settings.py
# 必要に応じて編集
```

### GCP 連携（任意）

staging 環境との Variables 同期や認証連携が必要な場合は [GCP 連携ガイド](docs/gcp-integration.md) を参照してください。

```bash
# GCP パッケージの追加インストール
make import-gcp
```

---

## コマンドリファレンス

### 基本コマンド

| コマンド | 説明 | パラメータ |
|---------|------|-----------|
| `make import` | uv 環境にプロジェクトをインストール | - |
| `make start` | 環境を起動（未作成なら自動作成） | `PORT=8090` |
| `make stop` | 環境の停止（コンテナは残る） | - |
| `make status` | 環境の設定とステータスを表示 | - |
| `make logs` | ログの表示 | `LINES=50` / `LINES=all` |
| `make remove` | 環境の削除 | - |
| `make recreate` | 環境を削除して再作成・起動 | - |
| `make clean` | `__pycache__` やビルド生成物を削除 | - |

### GCP 連携コマンド（オプション）

| コマンド | 説明 | パラメータ |
|---------|------|-----------|
| `make import-gcp` | GCP 連携パッケージをインストール | - |
| `make auth-user` | GCP ユーザー認証 | `PROJECT=...` |
| `make auth-sa` | GCP サービスアカウント認証 | `SERVICE_ACCOUNT=...` |
| `make sync-vars` | staging → ローカルへ Variables を同期 | `PROJECT=... LOCATION=... ENV_NAME=...` |
| `make sync-vars-sm` | Secret Manager 経由で Variables を同期 | `PROJECT=... LOCATION=... ENV_NAME=... SECRET_ID=...` |
| `make sync-settings` | Cloud Composer の設定を同期 | `PROJECT=... LOCATION=... ENV_NAME=...` |
| `make setup-connections` | Google Cloud のデフォルト接続を設定 | - |
| `make create-admin` | Airflow Admin ユーザーを作成 | `USERNAME=... PASSWORD=... EMAIL=...` |

詳細は [GCP 連携ガイド](docs/gcp-integration.md) を参照してください。

### よくあるワークフロー

```bash
# --- 初回セットアップ ---
make import          # 依存関係をインストール
make start           # 環境を作成して起動
# → 別ターミナルで http://localhost:8080 にアクセス

# --- 日常の開発 ---
make start           # 起動（Ctrl+C で停止）
# dags/ にファイルを追加・編集 → 再起動なしで反映

# --- 環境のリセット ---
make recreate        # まっさらな環境で再スタート

# --- ポートを変更して起動 ---
make start PORT=8090 # http://localhost:8090 でアクセス

# --- GCP 連携を追加する場合 ---
make import-gcp
make auth-user
make sync-vars PROJECT=your-project LOCATION=asia-northeast1 ENV_NAME=your-env
```

---

## DAG の追加とアップデート

- デフォルトの DAG ディレクトリ: `./dags`
- ファイルを更新すると再起動なしで反映されます（デフォルト10秒間隔）
- DAG ディレクトリは `composer_settings.py` の `DAGS_PATH` で変更可能

---

## 設定ファイル

`composer_settings.py.example` をコピーして `composer_settings.py` を作成すると、各種設定をカスタマイズできます。**GCP 未設定でもデフォルト値で動作する**ため、コピーは必須ではありません。

各設定項目の詳細は `composer_settings.py.example` を参照してください。

---

## セキュリティ

### 機密情報の管理

- `composer_settings.py` は `.gitignore` で除外
- `.example` ファイルからコピーして使用
- 機密情報は GCP Secret Manager で管理（GCP 連携使用時）

> **Warning**
> - 本ツールはローカル開発・テスト専用です
> - 管理者アカウント（admin/admin）は開発環境専用
> - サービスアカウントキーファイル（.json）を直接コミットしない

詳細は [SECURITY.md](SECURITY.md) をご確認ください。

---

## トラブルシューティング

<details>
<summary><strong>Docker がインストールされていない / 起動していない</strong></summary>

**エラー:** `docker: command not found` または `Cannot connect to the Docker daemon`

**対処:**
1. Docker Desktop がインストールされているか確認:
   ```bash
   docker --version
   ```
2. インストールされていない場合は [Docker Desktop](https://docs.docker.com/get-docker/) をインストール
3. インストール済みの場合は Docker Desktop アプリケーションを起動
4. 起動後、以下で確認:
   ```bash
   docker info
   ```

</details>

<details>
<summary><strong>Docker の権限エラー</strong></summary>

**エラー:** `permission denied while trying to connect to the Docker daemon socket`

**対処（Linux）:**
```bash
# 現在のユーザーを docker グループに追加
sudo usermod -aG docker $USER

# ログアウトして再ログイン、または以下を実行
newgrp docker
```

**対処（macOS）:** Docker Desktop が起動しているか確認してください。

</details>

<details>
<summary><strong>ポートが競合している</strong></summary>

**エラー:** `Bind for 0.0.0.0:8080 failed: port is already allocated`

**対処:**
```bash
# 別のポートで起動
make start PORT=8090

# または、8080 を使用しているプロセスを確認
lsof -i :8080
```

PostgreSQL のポート（デフォルト: 25432）が競合する場合は、`composer_settings.py` の `POSTGRES_LOCAL_PORT` を変更してください。

</details>

<details>
<summary><strong>Web サーバーに接続できない</strong></summary>

**症状:** `http://localhost:8080` にアクセスしても接続が拒否される

**対処:**
1. コンテナが起動しているか確認:
   ```bash
   make status
   ```
2. ログを確認して起動状況をチェック:
   ```bash
   make logs LINES=50
   ```
3. Web サーバーの起動には数分かかる場合があります。`make start` のログに `Listening at: http://0.0.0.0:8080` と表示されるまで待ってください
4. それでも接続できない場合は環境を再作成:
   ```bash
   make recreate
   ```

</details>

<details>
<summary><strong>メモリ不足</strong></summary>

**症状:** コンテナが突然停止する、または `Killed` と表示される

**対処:**
1. Docker Desktop の設定で割り当てメモリを **4GB 以上**に設定
   - macOS: Docker Desktop → Settings → Resources → Memory
   - Windows: Docker Desktop → Settings → Resources → Memory
2. 他の不要なコンテナを停止:
   ```bash
   docker ps                # 起動中のコンテナを確認
   docker stop <container>  # 不要なコンテナを停止
   ```

</details>

<details>
<summary><strong>Docker マウントエラー</strong></summary>

**対処:**
```bash
make recreate
```

</details>

<details>
<summary><strong>ログの確認方法</strong></summary>

```bash
# 最新50行を表示
make logs LINES=50

# 全ログを表示
make logs LINES=all

# Docker コンテナのログを直接確認
docker logs <container-id>
```

コンテナ ID は `docker ps` で確認できます。

</details>

<details>
<summary><strong>解決しない場合</strong></summary>

1. まず環境を再作成してみてください:
   ```bash
   make recreate
   ```

2. それでも解決しない場合は [Issue](../../issues/new) を作成してください。以下の情報を含めると解決が早くなります:
   - OS とバージョン（例: macOS 15.2, Ubuntu 24.04）
   - Docker のバージョン（`docker --version`）
   - エラーメッセージの全文
   - `make logs LINES=50` の出力

</details>

---

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

## ライセンス

このプロジェクトは Apache License 2.0 でライセンスされています。詳細は [LICENSE](LICENSE) をご覧ください。


**元プロジェクト:**
本プロジェクトは Google LLC の [composer-local-dev](https://github.com/GoogleCloudPlatform/composer-local-dev) を基に作成されています。

詳細な帰属情報については [NOTICE](NOTICE) ファイルをご確認ください。

---

## 貢献

Issue や Pull Request を歓迎します。大きな変更の場合は、まず Issue で議論してください。
