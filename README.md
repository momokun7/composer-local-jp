# Composer Local JP

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE) [![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![Airflow](https://img.shields.io/badge/Airflow-2.10.5-00C853?logo=apache-airflow&logoColor=white)](https://airflow.apache.org/) [![Docker](https://img.shields.io/badge/Docker-required-2496ED?logo=docker&logoColor=white)](https://www.docker.com/) ![Make](https://img.shields.io/badge/Make-required-6D4C41?logo=gnu&logoColor=white) ![uv](https://img.shields.io/badge/uv-required-DE5FE9?logo=astral&logoColor=white)

Google Cloud Composer（Apache Airflow）のローカル開発環境を日本語で簡単に構築・運用できるCLIです。

## 特徴

- **ローカルファースト** - GCP 設定不要でローカル開発可能
- **簡単セットアップ** - `make import && make start` だけで完全な Airflow 環境を構築（初回は自動作成）。`make import` は Airflow を含まない軽量な依存関係のみをインストールするため数秒で完了します。
- **GCP 連携はオプション** - Secret Manager・Airflow Variables（変数）同期が必要な場合のみ設定
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
| **uv** | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

- メモリ: Docker Desktop に **4GB 以上**を割り当ててください
- GCP と連携する場合のみ、[gcloud CLI](https://cloud.google.com/sdk/docs/install) が追加で必要です

---

## クイックスタート

```bash
# 1. リポジトリのクローン
git clone https://github.com/momokun7/composer-local-jp.git
cd composer-local-jp

# 2. 依存関係のインストール（数秒で完了します）
make import

# 3. 起動（初回は環境作成 + セットアップも自動実行）
make start
```

> **Note**: 初回起動時は Docker イメージのプルに数分〜十数分かかる場合があります。ネットワーク環境によって所要時間は異なります。2 回目以降はキャッシュが使われるため高速に起動します。

起動が完了すると `起動完了` と表示され、`Ctrl+C で停止します...` のメッセージが出ます。

> **別のターミナルを開いて** ブラウザで Airflow Web UI にアクセスしてください:
>
> **http://localhost:8080**
>
> ログイン不要です（`AUTH_ROLE_PUBLIC` が設定済みのため、認証なしでアクセスできます）。
>
> Airflow の DAGs 一覧が表示されれば起動成功です。

停止するには `Ctrl+C` を押してください。

> **Tip**: GCP の設定や `composer_settings.py` のコピーは不要です。デフォルト値で動作します。

### 停止と再起動

| 操作 | コマンド | 説明 |
|------|---------|------|
| 停止 | `make stop` | コンテナを停止します。データや設定は保持されます |
| 再起動 | `make restart` | 停止した環境をそのまま再起動します |
| リセット | `make remove` | 環境を完全に削除します。次回 `make start` で再作成されます |

### 設定のカスタマイズ（任意）

ポートやイメージバージョンを変更したい場合は、以下のようにコピーして編集してください。

```bash
cp composer_local/composer_settings.py.example composer_local/composer_settings.py
# 必要に応じて編集
```

### 複数環境の管理（任意）

環境名を変えることで、複数の独立した環境を並行稼働できます。

```bash
make start ENV=dev PORT=8080
make start ENV=staging PORT=8081   # 別ターミナルで
```

### GCP 連携（任意）

GCP プロジェクトとの Variables 同期や認証連携が必要な場合は、[GCP 連携ガイド](docs/gcp-integration.md) を参照してください。

```bash
# GCP 認証
make auth

# Variables の同期（GCP パッケージは自動でインストールされます）
make sync
```

---

## コマンドリファレンス

### 基本操作

| コマンド | 説明 | 変更例 |
|---------|------|-------|
| `make import` | 依存関係のインストールと pre-commit フックの設定（数秒で完了） | - |
| `make import-dags` | DAG 開発用に apache-airflow を追加インストール（IDE 補完用） | - |
| `make start` | 環境を起動（未作成なら自動作成） | `make start PORT=8090` でポート変更 |
| `make stop` | 環境の停止（コンテナは残る） | - |
| `make restart` | 環境を再起動 | - |
| `make status` | 環境の設定とステータスを表示 | - |
| `make logs` | ログの表示 | `make logs LINES=50 FOLLOW=1` で行数指定・追従 |

### GCP 連携コマンド（オプション）

| コマンド | 説明 | 主なオプション |
|---------|------|--------------|
| `make auth` | GCP ユーザー認証 | `SERVICE_ACCOUNT=sa@proj.iam.gserviceaccount.com` でSA権限借用 |
| `make sync` | Cloud Composer → ローカルへ Variables を同期 | `PROJECT=...`（任意） |
| `make sync SECRET_ID=xxx` | Secret Manager 経由で Variables を同期 | `SECRET_ID=your-secret-id` |
| `make sync SETTINGS=1` | Cloud Composer の設定を composer_settings.py に同期 | - |

詳細は [GCP 連携ガイド](docs/gcp-integration.md) を参照してください。

### メンテナンスコマンド

| コマンド | 説明 |
|---------|------|
| `make remove` | 環境の削除 |
| `make test` | テストを実行（pytest） |
| `make lint` | lint とフォーマットチェック |
| `make clean` | `__pycache__` やビルド生成物を削除 |

---

## DAG の開発

- デフォルトの DAG ディレクトリは `./dags` です
- ファイルを更新すると再起動なしで自動反映されます（デフォルト 10 秒間隔）
- DAG ディレクトリは `composer_settings.py` の `DAGS_PATH` で変更できます

### サンプル DAG

初期状態で `dags/print_hello_world.py` を用意しています。Airflow UI の DAGs 一覧で `hello_world_dag` が表示されることを確認してください。

### DAG の追加と反映

1. `dags/` ディレクトリに新しい `.py` ファイルを配置（ファイル名: `dag_id_*.py` など）
2. Airflow UI にアクセスして、DAGs 一覧をリロード（F5 キー）
3. ログで確認: `make logs LINES=50`（DAG パースエラーがないか確認）

### DAG のデバッグ

`run` サブコマンドを使って、コンテナ内で airflow コマンドを直接実行できます。

```bash
# DAG 構文エラーの確認
uv run -- composer-local run <ENV_NAME> -- dags list-import-errors

# DAG の一覧表示
uv run -- composer-local run <ENV_NAME> -- dags list

# DAG のテスト実行（EXECUTION_DATE は任意の日付）
uv run -- composer-local run <ENV_NAME> -- dags test DAG_ID EXECUTION_DATE
```

> **Tip**: `dags test` は実際のスケジューラを経由せず単一の DAG Run を実行するため、開発中のデバッグに便利です。

---

## DAG 開発時の IDE 補完（任意）

CLI 本体は Airflow に依存しないため、デフォルトではエディタで `from airflow import DAG` の補完が効きません。DAG を本格的に書く場合は以下を実行してください:

```bash
make import-dags
```

これで `apache-airflow`（コンテナと同一バージョン）がローカルの venv に入り、IDE の補完・型チェックが有効になります。日常の環境起動には不要です。

---

## シークレット管理

このリポジトリは多層防御でシークレットのコミット混入を防ぎます:

- `make import` 時に pre-commit フック（gitleaks / private key 検出）が自動で有効化されます
- CI でも gitleaks スキャンが実行されます
- 同期した Variables は gitignore 済みの `composer/` 配下にのみ保存されます
- `composer_settings.py` は gitignore 済みです（コミットされるのは `.example` のみ）

---

## プロジェクト構造

```
composer-local-jp/
├── .github/                    # CI/CD ワークフロー
├── Makefile                    # コマンドインターフェース
├── composer_local/             # メインパッケージ
│   ├── cli.py                  # CLI コマンド定義
│   ├── environment.py          # Docker 環境管理
│   ├── gcp_sync.py             # GCP 連携（Variables/設定同期・認証）
│   ├── docker_ops.py           # Docker コンテナ操作
│   ├── constants.py            # 定数・メッセージ
│   └── docker_files/           # コンテナ内ファイル
├── dags/                       # DAG ファイル
├── docs/                       # 追加ドキュメント
└── tests/                      # テスト
```

---

## 設定ファイル

`composer_settings.py.example` をコピーして `composer_settings.py` を作成すると、各種設定をカスタマイズできます。**GCP 未設定でもデフォルト値で動作する**ため、コピーは必須ではありません。

各設定項目の詳細は、`composer_settings.py.example` のコメントを参照してください。

---

## セキュリティ

- `composer_settings.py` は `.gitignore` で除外されています
- 機密情報は GCP Secret Manager で管理してください（GCP 連携使用時）

> [!WARNING]
> 本ツールはローカル開発・テスト専用です。管理者アカウント（admin/admin）やログインスキップ設定は開発環境のみで使用してください。

詳細は [SECURITY.md](SECURITY.md) を参照してください。

---

## アップグレード

リポジトリの最新版に更新するには、以下のコマンドを実行してください。

```bash
git pull && make import
```

---

## トラブルシューティング

<details>
<summary><strong>uv がインストールされていない</strong></summary>

**エラー:** `uv: command not found` または `make import` 実行時にエラーが発生する

**対処:**

`uv` は Python パッケージマネージャーです。以下のコマンドでインストールしてください。

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Homebrew（macOS）
brew install uv
```

インストール後、シェルを再起動するか `source ~/.bashrc`（または `~/.zshrc`）を実行してください。

詳細は [uv 公式ドキュメント](https://docs.astral.sh/uv/getting-started/installation/) を参照してください。

</details>

<details>
<summary><strong>Docker がインストールされていない / 起動していない</strong></summary>

**エラー:** `docker: command not found` または `Cannot connect to the Docker daemon`

**対処:**
```bash
# Docker の状態を確認
docker info

# Docker Desktop が起動していない場合はアプリケーションを起動してください
```

**Linux の場合:** `sudo usermod -aG docker $USER` で権限を設定後、再ログインしてください。

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
<summary><strong>メモリ不足 / コンテナが停止する</strong></summary>

**症状:** コンテナが突然停止する、または `Killed` と表示される

**対処:** Docker Desktop の設定でメモリを **4GB 以上**に割り当ててください。
- macOS: Docker Desktop → Settings → Resources → Memory
- Windows: Docker Desktop → Settings → Resources → Memory

</details>

<details>
<summary><strong>GCP 認証エラー（make sync 実行時）</strong></summary>

**エラー:** `Permission denied` や `Application Default Credentials not found`

**対処:**
```bash
make auth
# サービスアカウントの場合:
make auth SERVICE_ACCOUNT=xxx@yyy.iam.gserviceaccount.com
```

</details>

<details>
<summary><strong>make import が失敗する</strong></summary>

**対処:**
```bash
uv cache clean
rm -rf .venv
make import
```

</details>

<details>
<summary><strong>解決しない場合</strong></summary>

1. まず環境を再作成してみてください:
   ```bash
   make remove
   make start
   ```

2. それでも解決しない場合は [Issue](../../issues/new) を作成してください。以下の情報を含めると解決が早くなります:
   - OS とバージョン
   - `docker --version` の出力
   - エラーメッセージの全文
   - `make logs LINES=50` の出力

</details>

---

## ライセンス

このプロジェクトは [Apache License 2.0](LICENSE) でライセンスされています。

元プロジェクト: Google LLC の [composer-local-dev](https://github.com/GoogleCloudPlatform/composer-local-dev)（詳細は [NOTICE](NOTICE)）

---

## 貢献

Issue や Pull Request を歓迎しています。大きな変更の場合は、まず Issue で議論してください。
