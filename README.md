# Composer Local JP

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE) [![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![Airflow](https://img.shields.io/badge/Airflow-2.10.2-00C853?logo=apache-airflow&logoColor=white)](https://airflow.apache.org/) [![Docker](https://img.shields.io/badge/Docker-required-2496ED?logo=docker&logoColor=white)](https://www.docker.com/) ![Make](https://img.shields.io/badge/Make-required-6D4C41?logo=gnu&logoColor=white) ![uv](https://img.shields.io/badge/uv-required-DE5FE9?logo=astral&logoColor=white)

Google Cloud Composer（Apache Airflow）のローカル開発環境を日本語で簡単に構築・運用できるCLIです。

## 特徴

- **ローカルファースト** - GCP 設定不要で `make create && make start` だけで Airflow が動く
- **簡単セットアップ** - `make create` 一発で完全な Airflow 環境を構築
- **GCP 連携はオプション** - Secret Manager・staging 同期が必要な場合のみ設定
- **Composer 3 対応** - 最新の Airflow 2.10.2 + PostgreSQL
- **uv による高速な依存関係管理**

> 本プロジェクトは Google LLC の [GoogleCloudPlatform/composer-local-dev](https://github.com/GoogleCloudPlatform/composer-local-dev)（Apache License 2.0）を基に、日本語環境向けに最適化したものです。


---

## クイックスタート

```bash
# 1. リポジトリのクローン
git clone <repository-url>
cd composer-local-jp

# 2. 依存関係のインストール
make import

# 3. 起動（初回は環境作成 + セットアップも自動実行）
make start

# ブラウザでAirflow Web UIにアクセス
# http://localhost:8080
# ユーザー名: admin / パスワード: admin

# 停止する場合は Ctrl+C
```

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
| `make start` | 環境を起動（未作成なら自動作成＋セットアップ、Ctrl+C で停止） |
| `make stop` | 環境の停止 |
| `make status` | 環境の状態確認 |
| `make logs` | ログの表示 |
| `make remove` | 環境の削除 |
| `make recreate` | 環境を削除して再作成 |

### GCP 連携コマンド（オプション）

| コマンド | 説明 |
|---------|------|
| `make import-gcp` | GCP 連携パッケージをインストール |
| `make auth-user` | GCP ユーザー認証 |
| `make auth-sa` | GCP サービスアカウント認証 |
| `make sync-vars` | staging → ローカルへ Variables を同期 |
| `make sync-settings` | Cloud Composer の設定を同期 |

詳細は [GCP 連携ガイド](docs/gcp-integration.md) を参照してください。

> **Warning**
> `make start` はフォアグラウンドで実行されます。localhostにアクセスする場合は別のターミナルを使用してください。

---

## DAG の追加とアップデート

- デフォルトの DAG ディレクトリ: `./dags`
- ファイルを更新すると再起動なしで反映されます

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
