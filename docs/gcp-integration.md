# GCP 連携ガイド

このドキュメントでは、ローカル Composer 環境を Google Cloud Platform（GCP）と連携させる手順を説明します。

> **Note**: GCP 連携はオプションです。ローカルで DAG を開発・テストするだけであれば、GCP の設定は不要です。

## GCP 連携が必要なケース

以下のようなユースケースで GCP 連携が役立ちます：

- **本番の Airflow Variables（変数）をローカルで使いたい場合**: 本番環境の Variables、接続設定、認証情報などをローカル環境に同期して、本番同等の環境でテストできます。
- **本番同等の接続設定をテストしたい場合**: Cloud SQL、BigQuery、GCS などのリソースへの接続設定を本番同等の状態でテストし、DAG の動作を確認できます。
- **Secret Manager で集中管理されたシークレットを使いたい場合**: 環境間でシークレット管理を統一し、セキュアな設定情報を同期できます。

## 前提条件

- [Google Cloud SDK (gcloud)](https://cloud.google.com/sdk/docs/install) がインストールされていること
- GCP プロジェクトへのアクセス権があること

## セットアップ

### 1. GCP パッケージのインストール

```bash
make import-gcp
# または
uv sync --extra gcp
```

### 2. 設定ファイルの編集

まず設定ファイルをコピーします:

```bash
cp composer_local/composer_settings.py.example composer_local/composer_settings.py
```

`composer_local/composer_settings.py` の GCP セクションのコメントアウトを解除して値を設定します:

```python
# Cloud Composer 環境の識別情報
COMPOSER_ENV_NAME = "your-composer-env-name"
COMPOSER_LOCATION = "asia-northeast1"

# プロジェクトID（staging環境）
PROJECT_ID = "your-staging-project-id"

# サービスアカウント設定
SERVICE_ACCOUNT = "your-sa@your-project.iam.gserviceaccount.com"

# Secret Manager を使う場合
SECRET_ID = "local_composer_airflow_variables"
```

設定ファイルを使わず、コマンドラインで直接指定することもできます:

```bash
make sync-vars PROJECT=xxx LOCATION=xxx ENV_NAME=xxx
```

### 3. 認証

#### ユーザー認証（個人アカウント）

```bash
make auth-user
```

#### サービスアカウント認証（staging 環境と同等の権限）

```bash
make auth-sa SERVICE_ACCOUNT=your-sa@your-project.iam.gserviceaccount.com
```

## Variables の同期

staging 環境の Airflow Variables をローカルに同期する方法は 2 つあります。

### 方法 1: 直接同期（推奨）

Secret Manager を経由せず、Cloud Composer から直接 Variables を取得します。

- **メリット**: セットアップが簡単。Secret Manager の設定が不要
- **デメリット**: Cloud Composer 環境への直接アクセス権限が必要

```bash
make sync-vars
# または設定ファイルなしで実行
make sync-vars PROJECT=xxx LOCATION=xxx ENV_NAME=xxx
```

### 方法 2: Secret Manager 経由

Cloud Composer → Secret Manager → ローカル環境の順に同期します。

- **メリット**: シークレットを一元管理できる。チーム間で設定を共有しやすい
- **デメリット**: Secret Manager の追加設定が必要

```bash
make sync-vars-sm
# または設定ファイルなしで実行（SECRET_ID を指定）
make sync-vars-sm SECRET_ID=your-secret-id
```

Secret Manager のシークレット ID は `composer_settings.py` で設定するか、上記のようにコマンドラインで直接指定できます。

## 設定の同期

Cloud Composer の設定を `composer_settings.py` に同期できます:

```bash
make sync-settings
```

## コマンド一覧

| コマンド | 説明 |
|---------|------|
| `make import-gcp` | GCP 連携パッケージをインストール |
| `make auth-user` | GCP ユーザー認証 |
| `make auth-sa` | GCP サービスアカウント認証 |
| `make sync-vars` | Cloud Composer → ローカルへ Variables を直接同期 |
| `make sync-vars-sm` | Secret Manager 経由で Variables を同期 |
| `make sync-settings` | Cloud Composer の設定を同期 |
